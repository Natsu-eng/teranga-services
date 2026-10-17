import { existsSync, readFileSync } from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';

/**
 * Application installable (PWA) : ce que Chrome Android et Safari iOS
 * exigent pour proposer l'installation en plein écran, vérifié sur les
 * fichiers réellement servis (public/, index.html, en-têtes de déploiement).
 */
const root = path.resolve(__dirname, '..');
const publicDir = path.join(root, 'public');

interface ManifestIcon {
  src: string;
  sizes: string;
  type: string;
  purpose?: string;
}

const manifest = JSON.parse(
  readFileSync(path.join(publicDir, 'manifest.webmanifest'), 'utf-8'),
) as {
  name: string;
  short_name: string;
  start_url: string;
  scope: string;
  display: string;
  theme_color: string;
  background_color: string;
  icons: ManifestIcon[];
};
const indexHtml = readFileSync(path.join(root, 'index.html'), 'utf-8');

/** Largeur, hauteur et type de couleur lus dans l'en-tête IHDR d'un PNG. */
function pngInfo(publicPath: string): { width: number; height: number; colorType: number } {
  const bytes = readFileSync(path.join(publicDir, publicPath));
  expect(bytes.subarray(1, 4).toString('ascii'), publicPath).toBe('PNG');
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20), colorType: bytes[25] };
}

function metaContent(name: string): string | undefined {
  return new RegExp(`<meta name="${name}" content="([^"]*)"`).exec(indexHtml)?.[1];
}

describe('manifeste de l’application installable', () => {
  it('porte le nom Téranga et s’ouvre en plein écran sur toute l’app', () => {
    expect(manifest.name).toBe('Téranga');
    expect(manifest.short_name).toBe('Téranga');
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBe('/');
    expect(manifest.scope).toBe('/');
  });

  it('reprend les couleurs de la page (pas de flash de couleur au lancement)', () => {
    expect(manifest.background_color).toBe('#fcf9f8');
    expect(manifest.theme_color).toBe(metaContent('theme-color'));
  });

  it('fournit des icônes PNG 192 et 512 px qui existent aux bonnes dimensions', () => {
    for (const icon of manifest.icons) {
      const [width, height] = icon.sizes.split('x').map(Number);
      expect(icon.type).toBe('image/png');
      expect(existsSync(path.join(publicDir, icon.src)), icon.src).toBe(true);
      const info = pngInfo(icon.src);
      expect([info.width, info.height], icon.src).toEqual([width, height]);
    }
    const anySizes = manifest.icons
      .filter((icon) => icon.purpose === 'any')
      .map((icon) => icon.sizes);
    expect(anySizes).toEqual(expect.arrayContaining(['192x192', '512x512']));
  });

  it('propose une icône « maskable » pour les lanceurs Android', () => {
    const maskable = manifest.icons.find((icon) => icon.purpose === 'maskable');
    expect(maskable?.sizes).toBe('512x512');
  });
});

describe('index.html : installation Android et iPhone', () => {
  it('déclare le manifeste', () => {
    expect(indexHtml).toContain('<link rel="manifest" href="/manifest.webmanifest" />');
  });

  it('fournit l’icône d’écran d’accueil iOS : 180 px, opaque', () => {
    const href = /<link rel="apple-touch-icon" href="([^"]+)"/.exec(indexHtml)?.[1];
    expect(href).toBe('/icons/apple-touch-icon.png');
    const info = pngInfo(href!);
    expect([info.width, info.height]).toEqual([180, 180]);
    // Type de couleur PNG 2 = RVB sans canal alpha (iOS remplirait la transparence en noir).
    expect(info.colorType).toBe(2);
  });

  it('active le mode plein écran iOS, sans chevauchement de la barre d’état', () => {
    expect(metaContent('apple-mobile-web-app-capable')).toBe('yes');
    expect(metaContent('mobile-web-app-capable')).toBe('yes');
    expect(metaContent('apple-mobile-web-app-title')).toBe('Téranga');
    expect(metaContent('apple-mobile-web-app-status-bar-style')).toBe('default');
  });
});

describe('en-têtes de déploiement de la PWA (Vercel et Caddy)', () => {
  const vercel = JSON.parse(readFileSync(path.join(root, 'vercel.json'), 'utf-8')) as {
    headers: { source: string; headers: { key: string; value: string }[] }[];
  };
  const caddyfile = readFileSync(path.join(root, 'Caddyfile'), 'utf-8');

  function vercelHeader(source: string, key: string): string | undefined {
    return vercel.headers.find((rule) => rule.source === source)?.headers.find((h) => h.key === key)
      ?.value;
  }

  it('Vercel : sw.js et le manifeste toujours revalidés, manifeste au bon type', () => {
    expect(vercelHeader('/sw.js', 'Cache-Control')).toBe('no-cache');
    expect(vercelHeader('/manifest.webmanifest', 'Cache-Control')).toBe('no-cache');
    expect(vercelHeader('/manifest.webmanifest', 'Content-Type')).toBe('application/manifest+json');
  });

  it('Caddy : tout sauf /assets/ revalidé (routes SPA, sw.js, manifeste), manifeste au bon type', () => {
    expect(caddyfile).toMatch(
      /@revalidated not path \/assets\/\*\n\theader @revalidated Cache-Control "no-cache"/,
    );
    expect(caddyfile).toMatch(
      /@assets path \/assets\/\*\n\theader @assets Cache-Control "public, max-age=31536000, immutable"/,
    );
    expect(caddyfile).toMatch(
      /@manifest path \/manifest\.webmanifest\n\theader @manifest Content-Type "application\/manifest\+json"/,
    );
  });

  it('la CSP autorise le service worker et le manifeste (même origine)', () => {
    const csp = vercelHeader('/(.*)', 'Content-Security-Policy') ?? '';
    // worker-src et manifest-src absents : repli sur script-src / default-src 'self'.
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("default-src 'self'");
    expect(csp).not.toMatch(/worker-src|manifest-src/);
  });
});
