import vm from 'node:vm';
import type { Plugin } from 'vite';
import { describe, expect, it, vi } from 'vitest';
import {
  renderServiceWorker,
  serviceWorkerBuild,
  serviceWorkerPlugin,
  shellAssetsFromHtml,
  type ServiceWorkerBuild,
} from './serviceWorkerPlugin';

/**
 * Le service worker PRODUIT (modèle pwa/sw.js + SW_BUILD) est exécuté pour
 * de vrai dans un bac à sable `node:vm`, avec de faux `caches` et `fetch` :
 * on prouve ce qu'il intercepte, ce qu'il met en cache... et surtout ce
 * qu'il ne touche JAMAIS (API, authentifié, autre origine, non-GET).
 */

const ORIGIN = 'https://teranga.example';
const BUILD: ServiceWorkerBuild = {
  version: 'v2',
  shell: ['/index.html', '/assets/index-abc.js', '/assets/index-def.css'],
};

interface FakeResponse {
  ok: boolean;
  status: number;
  type: string;
  body: string;
  headers: Headers;
  clone(): FakeResponse;
}

function response(
  body: string,
  init: { status?: number; type?: string; headers?: Record<string, string> } = {},
): FakeResponse {
  const status = init.status ?? 200;
  const res: FakeResponse = {
    ok: status >= 200 && status < 300,
    status,
    type: init.type ?? 'basic',
    body,
    headers: new Headers(init.headers),
    clone: () => res,
  };
  return res;
}

interface FakeRequest {
  url: string;
  method: string;
  mode: string;
  headers: Headers;
  cache?: string;
}

function request(
  path: string,
  init: Partial<Omit<FakeRequest, 'headers'>> & { headers?: Record<string, string> } = {},
): FakeRequest {
  return {
    url: path.startsWith('http') ? path : `${ORIGIN}${path}`,
    method: init.method ?? 'GET',
    mode: init.mode ?? 'cors',
    headers: new Headers(init.headers),
  };
}

const keyOf = (req: string | FakeRequest) =>
  typeof req === 'string' ? `${ORIGIN}${req}` : req.url;

/** Charge le service worker produit dans un environnement simulé. */
function loadServiceWorker(initialCaches: Record<string, Record<string, FakeResponse>> = {}) {
  const listeners = new Map<string, (event: unknown) => void>();
  const store = new Map<string, Map<string, FakeResponse>>(
    Object.entries(initialCaches).map(([name, entries]) => [
      name,
      new Map(Object.entries(entries).map(([path, res]) => [keyOf(path), res])),
    ]),
  );
  const network = vi.fn<(req: FakeRequest) => Promise<FakeResponse>>();

  const openCache = (name: string) => {
    if (!store.has(name)) store.set(name, new Map());
    const entries = store.get(name)!;
    return {
      async addAll(requests: FakeRequest[]) {
        for (const req of requests) {
          const res = await network(req);
          if (!res.ok) throw new TypeError(`échec ${req.url}`);
          entries.set(req.url, res);
        }
      },
      async match(req: string | FakeRequest) {
        return entries.get(keyOf(req));
      },
      async put(req: FakeRequest, res: FakeResponse) {
        entries.set(req.url, res);
      },
    };
  };

  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, listener: (event: unknown) => void) =>
      listeners.set(type, listener),
    skipWaiting: vi.fn(async () => undefined),
    clients: { claim: vi.fn(async () => undefined) },
  };
  const caches = {
    open: async (name: string) => openCache(name),
    keys: async () => [...store.keys()],
    delete: async (name: string) => store.delete(name),
    match: async (req: string, options: { cacheName: string }) =>
      store.get(options.cacheName)?.get(keyOf(req)),
  };
  class Request {
    url: string;
    cache?: string;
    constructor(url: string, init: { cache?: string } = {}) {
      this.url = keyOf(url);
      this.cache = init.cache;
    }
  }

  vm.runInNewContext(renderServiceWorker(BUILD), {
    self,
    caches,
    fetch: network,
    Request,
    URL,
    Promise,
    console,
  });

  /** Déclenche un événement ; renvoie la promesse passée à waitUntil/respondWith (ou null). */
  function dispatch(type: 'install' | 'activate', event: object = {}): Promise<unknown> {
    let pending: Promise<unknown> = Promise.resolve();
    listeners.get(type)!({ ...event, waitUntil: (p: Promise<unknown>) => (pending = p) });
    return pending;
  }

  function fetchEvent(req: FakeRequest): Promise<FakeResponse> | null {
    let responded: Promise<FakeResponse> | null = null;
    listeners.get('fetch')!({
      request: req,
      respondWith: (p: Promise<FakeResponse>) => (responded = p),
    });
    return responded;
  }

  return {
    self,
    store,
    network,
    dispatch,
    fetchEvent,
    cacheName: `teranga-shell-${BUILD.version}`,
  };
}

describe('service worker : mises à jour propres', () => {
  it('précache la coquille depuis le serveur (jamais le cache HTTP) puis prend la main sans attendre', async () => {
    const sw = loadServiceWorker();
    sw.network.mockImplementation(async (req) => response(`contenu ${req.url}`));

    await sw.dispatch('install');

    const requested = sw.network.mock.calls.map(([req]) => [req.url, req.cache]);
    expect(requested).toEqual(BUILD.shell.map((path) => [`${ORIGIN}${path}`, 'reload']));
    expect([...sw.store.get(sw.cacheName)!.keys()]).toEqual(
      BUILD.shell.map((path) => `${ORIGIN}${path}`),
    );
    expect(sw.self.skipWaiting).toHaveBeenCalledOnce();
  });

  it("n'installe rien si un fichier de la coquille manque : l'ancienne version reste en place", async () => {
    const sw = loadServiceWorker();
    sw.network.mockImplementation(async (req) =>
      response('', { status: req.url.endsWith('.css') ? 404 : 200 }),
    );

    await expect(sw.dispatch('install')).rejects.toThrow();
    expect(sw.self.skipWaiting).not.toHaveBeenCalled();
  });

  it('à l’activation, supprime les caches des versions précédentes, et seulement eux', async () => {
    const sw = loadServiceWorker({
      'teranga-shell-v1': {},
      'teranga-shell-v2': {},
      'autre-usage': {},
    });

    await sw.dispatch('activate');

    expect([...sw.store.keys()].sort()).toEqual(['autre-usage', 'teranga-shell-v2']);
    expect(sw.self.clients.claim).toHaveBeenCalledOnce();
  });
});

describe('service worker : ce qu’il ne touche JAMAIS', () => {
  it.each([
    ['API en GET', request('/api/v1/artisans')],
    ['API, navigation directe', request('/api/v1/health', { mode: 'navigate' })],
    ['API, racine', request('/api')],
    [
      'requête authentifiée',
      request('/assets/index-abc.js', { headers: { Authorization: 'Bearer jeton' } }),
    ],
    ['POST', request('/assets/index-abc.js', { method: 'POST' })],
    ['navigation POST', request('/connexion', { method: 'POST', mode: 'navigate' })],
    ['backend sur une autre origine', request('https://api.teranga.example/api/v1/users/me')],
    ['document via URL signée', request('https://stockage.example/documents/cni.jpg?signature=x')],
    ['autre origine, chemin /assets', request('https://cdn.example/assets/x.js')],
    ['image publique non hachée', request('/images/accueil.webp')],
    ['manifeste', request('/manifest.webmanifest')],
    ['service worker lui-même', request('/sw.js')],
  ])('%s : laissé au navigateur', (_label, req) => {
    const sw = loadServiceWorker();
    expect(sw.fetchEvent(req)).toBeNull();
    expect(sw.network).not.toHaveBeenCalled();
  });
});

describe('service worker : pages en réseau d’abord', () => {
  it('sert la page du réseau même si une coquille est en cache, sans la mettre en cache', async () => {
    const sw = loadServiceWorker({
      'teranga-shell-v2': { '/index.html': response('ancienne coquille') },
    });
    sw.network.mockResolvedValue(response('page fraîche'));

    const served = await sw.fetchEvent(request('/accueil', { mode: 'navigate' }));

    expect(served?.body).toBe('page fraîche');
    expect([...sw.store.get(sw.cacheName)!.keys()]).toEqual([`${ORIGIN}/index.html`]);
  });

  it('hors connexion, se replie sur la coquille en cache', async () => {
    const sw = loadServiceWorker({ 'teranga-shell-v2': { '/index.html': response('coquille') } });
    sw.network.mockRejectedValue(new TypeError('Failed to fetch'));

    const served = await sw.fetchEvent(request('/profil', { mode: 'navigate' }));

    expect(served?.body).toBe('coquille');
  });

  it("hors connexion et sans coquille, l'échec réseau d'origine remonte", async () => {
    const sw = loadServiceWorker();
    sw.network.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(sw.fetchEvent(request('/profil', { mode: 'navigate' }))).rejects.toThrow(
      'Failed to fetch',
    );
  });

  it("n'utilise jamais la coquille d'une autre version", async () => {
    const sw = loadServiceWorker({
      'teranga-shell-v1': { '/index.html': response('vieille coquille') },
    });
    sw.network.mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(sw.fetchEvent(request('/', { mode: 'navigate' }))).rejects.toThrow();
  });
});

describe('service worker : fichiers hachés en cache d’abord', () => {
  it('met en cache un asset à la première demande, puis le sert sans réseau', async () => {
    const sw = loadServiceWorker();
    sw.network.mockResolvedValue(response('code'));

    expect((await sw.fetchEvent(request('/assets/index-abc.js')))?.body).toBe('code');
    expect((await sw.fetchEvent(request('/assets/index-abc.js')))?.body).toBe('code');

    expect(sw.network).toHaveBeenCalledOnce();
  });

  it.each([
    ['erreur serveur', response('', { status: 500 })],
    ['réponse opaque', response('', { type: 'opaque' })],
    ['no-store', response('x', { headers: { 'Cache-Control': 'no-store' } })],
    ['private', response('x', { headers: { 'Cache-Control': 'private, max-age=60' } })],
  ])('ne garde jamais une réponse « %s »', async (_label, res) => {
    const sw = loadServiceWorker();
    sw.network.mockResolvedValue(res);

    await sw.fetchEvent(request('/assets/index-abc.js'));

    expect(sw.store.get(sw.cacheName)?.size ?? 0).toBe(0);
  });
});

describe('plugin de build du service worker', () => {
  const html =
    '<script type="module" crossorigin src="/assets/index-abc.js"></script>' +
    '<link rel="stylesheet" crossorigin href="/assets/index-def.css">' +
    '<link rel="icon" href="/favicon.svg"><link rel="manifest" href="/manifest.webmanifest">';

  it("ne précache que index.html et les fichiers /assets/ qu'il charge", () => {
    expect(shellAssetsFromHtml(html)).toEqual(['/assets/index-abc.js', '/assets/index-def.css']);
    expect(serviceWorkerBuild(html, ['index.html']).shell).toEqual([
      '/index.html',
      '/assets/index-abc.js',
      '/assets/index-def.css',
    ]);
  });

  it('version stable pour un build identique, nouvelle dès que le contenu change', () => {
    const files = ['index.html', 'assets/index-abc.js', 'assets/police-1.woff2'];
    const version = serviceWorkerBuild(html, files).version;

    expect(serviceWorkerBuild(html, [...files].reverse()).version).toBe(version);
    expect(serviceWorkerBuild(html.replace('index-abc', 'index-xyz'), files).version).not.toBe(
      version,
    );
    expect(serviceWorkerBuild(html, [...files, 'assets/police-2.woff2']).version).not.toBe(version);
    expect(version).toMatch(/^[0-9a-f]{16}$/);
  });

  it('produit un script strict, avec SW_BUILD défini avant le modèle', () => {
    const script = renderServiceWorker(BUILD, '/* modèle */');
    expect(script.split('\n')).toEqual([
      "'use strict';",
      `const SW_BUILD = ${JSON.stringify(BUILD)};`,
      '/* modèle */',
    ]);
  });

  function runGenerateBundle(bundle: Record<string, unknown>) {
    const plugin = serviceWorkerPlugin() as Plugin & {
      generateBundle: (this: unknown, options: unknown, bundle: unknown) => void;
    };
    const emitted: { fileName: string; source: string }[] = [];
    const context = {
      emitFile: (file: { fileName: string; source: string }) => emitted.push(file),
      error: (message: string) => {
        throw new Error(message);
      },
    };
    plugin.generateBundle.call(context, {}, bundle);
    return { plugin, emitted };
  }

  it('émet dist/sw.js au build seulement, après index.html', () => {
    const { plugin, emitted } = runGenerateBundle({
      'index.html': { type: 'asset', source: html },
      'assets/index-abc.js': { type: 'chunk' },
    });

    expect(plugin.apply).toBe('build');
    expect(plugin.enforce).toBe('post');
    expect(emitted).toHaveLength(1);
    expect(emitted[0].fileName).toBe('sw.js');
    expect(emitted[0].source).toContain('"/assets/index-abc.js"');
    expect(emitted[0].source).toContain("self.addEventListener('fetch'");
  });

  it('échoue franchement si index.html est absent du bundle', () => {
    expect(() => runGenerateBundle({})).toThrow(/index\.html introuvable/);
  });
});
