/* global SW_BUILD */
/*
 * Service worker de Téranga (application installable, DEPLOYMENT.md « PWA »).
 *
 * MODÈLE : ce fichier n'est pas servi tel quel. Au build, le plugin
 * pwa/serviceWorkerPlugin.ts le préfixe d'une constante `SW_BUILD`
 * ({ version, shell }) et l'émet en dist/sw.js. `version` change à chaque
 * build dont le contenu change : le navigateur voit alors un nouveau
 * service worker et la mise à jour se fait seule (voir « Mises à jour »).
 *
 * Volontairement MINIMAL et PRUDENT. Le service worker n'intercepte QUE :
 * - les navigations (pages de l'app) : RÉSEAU D'ABORD, toujours. La page en
 *   cache ne sert que hors connexion (repli sur la coquille index.html) ;
 *   une réponse de navigation n'est jamais mise en cache ;
 * - les fichiers hachés de /assets/ (JS, CSS, polices) : immuables par
 *   construction (le nom change si le contenu change), donc servis depuis
 *   le cache sans risque d'obsolescence.
 *
 * Il ne touche JAMAIS (le navigateur fait alors sa requête normale) :
 * - l'API (/api/...) : aucune donnée métier en cache, jamais de donnée
 *   périmée ni de réponse authentifiée stockée sur l'appareil ;
 * - toute requête autre que GET, toute requête portant un en-tête
 *   Authorization, toute requête vers une autre origine (backend séparé,
 *   stockage objet, documents d'identité via URL signée...) ;
 * - toute réponse en erreur, opaque ou marquée no-store / private.
 *
 * Mises à jour : `skipWaiting` + `clients.claim` (la nouvelle version prend
 * la main tout de suite) et suppression des caches des versions
 * précédentes à l'activation. Comme les pages viennent toujours du réseau
 * d'abord, aucune version ne peut rester « bloquée » sur l'appareil.
 *
 * Mode strict : la directive 'use strict' est posée par le plugin en TOUTE
 * première ligne du fichier produit (ici, après SW_BUILD, elle serait sans effet).
 */

const CACHE_PREFIX = 'teranga-shell-';
const CACHE_NAME = CACHE_PREFIX + SW_BUILD.version;
// Coquille : index.html et les fichiers qu'il charge (JS et CSS d'entrée).
const SHELL_URLS = SW_BUILD.shell;
const OFFLINE_FALLBACK = '/index.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      // `cache: 'reload'` : copie fraîche du serveur, jamais celle du cache
      // HTTP. Si un seul fichier échoue, l'installation échoue en bloc et
      // l'ancienne version reste en place (jamais de coquille incomplète).
      .then((cache) => cache.addAll(SHELL_URLS.map((url) => new Request(url, { cache: 'reload' }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            // Seuls NOS caches périmés : jamais ceux d'un autre usage.
            .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

/** 'navigation', 'asset' ou null (requête laissée au navigateur). */
function strategyFor(request) {
  if (request.method !== 'GET') return null;
  if (request.headers.has('Authorization')) return null;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return null;
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return null;
  if (request.mode === 'navigate') return 'navigation';
  if (url.pathname.startsWith('/assets/')) return 'asset';
  return null;
}

/** Vrai si la réponse peut être gardée sur l'appareil. */
function isCacheable(response) {
  if (!response || !response.ok || response.type !== 'basic') return false;
  const cacheControl = (response.headers.get('Cache-Control') || '').toLowerCase();
  return !cacheControl.includes('no-store') && !cacheControl.includes('private');
}

async function networkFirstNavigation(request) {
  try {
    return await fetch(request);
  } catch (error) {
    // Hors connexion : la coquille de l'app (elle affichera ses propres
    // messages d'erreur réseau). Sans coquille en cache, l'échec d'origine.
    const shell = await caches.match(OFFLINE_FALLBACK, { cacheName: CACHE_NAME });
    if (shell) return shell;
    throw error;
  }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (isCacheable(response)) {
    await cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  const strategy = strategyFor(event.request);
  if (strategy === 'navigation') {
    event.respondWith(networkFirstNavigation(event.request));
  } else if (strategy === 'asset') {
    event.respondWith(cacheFirstAsset(event.request));
  }
  // Sinon : aucun respondWith, la requête suit le chemin normal du navigateur.
});
