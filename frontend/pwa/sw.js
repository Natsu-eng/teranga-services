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
 * Notifications push (DEPLOYMENT.md §15) : `push` affiche la notification
 * envoyée par le backend (contenu sobre, chiffré de bout en bout jusqu'ici),
 * `notificationclick` ouvre la conversation concernée. Le lien est CONTRÔLÉ :
 * seulement un chemin /messages de cette origine, sinon la liste des
 * messages -- jamais une adresse externe, même si le contenu était altéré.
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

// --------------------------------------------------------------- Notifications

// Repli si le contenu reçu est absent ou illisible : une notification
// s'affiche TOUJOURS (les navigateurs l'exigent pour chaque push reçu).
const DEFAULT_NOTIFICATION = {
  title: 'Téranga',
  body: 'Nouveau message sur Téranga',
  url: '/messages',
  tag: 'teranga-message',
};
const NOTIFICATION_ICON = '/icons/icon-192.png';
const MAX_TEXT_LENGTH = 120;
// Seules pages ouvrables depuis une notification : la liste des messages ou un fil.
const MESSAGES_PATH = /^\/messages(\/[A-Za-z0-9-]{1,64})?$/;
const SAFE_TAG = /^[A-Za-z0-9-]{1,80}$/;

/** Chemin /messages[/id] de CETTE origine, ou null. */
function safeAppPath(value) {
  if (typeof value !== 'string') return null;
  let url;
  try {
    url = new URL(value, self.location.origin);
  } catch {
    return null;
  }
  if (url.origin !== self.location.origin || !MESSAGES_PATH.test(url.pathname)) return null;
  return url.pathname;
}

function shortText(value, fallback) {
  return typeof value === 'string' && value.trim()
    ? value.trim().slice(0, MAX_TEXT_LENGTH)
    : fallback;
}

/** Contenu affichable d'un événement push, toujours valide. */
function notificationFromPush(event) {
  let data = {};
  try {
    data = (event.data && event.data.json()) || {};
  } catch {
    data = {};
  }
  return {
    title: shortText(data.title, DEFAULT_NOTIFICATION.title),
    body: shortText(data.body, DEFAULT_NOTIFICATION.body),
    url: safeAppPath(data.url) || DEFAULT_NOTIFICATION.url,
    tag:
      typeof data.tag === 'string' && SAFE_TAG.test(data.tag) ? data.tag : DEFAULT_NOTIFICATION.tag,
  };
}

self.addEventListener('push', (event) => {
  const notification = notificationFromPush(event);
  event.waitUntil(
    self.registration.showNotification(notification.title, {
      body: notification.body,
      // Un fil = une notification (remplacée, mais signalée à nouveau).
      tag: notification.tag,
      renotify: true,
      icon: NOTIFICATION_ICON,
      badge: NOTIFICATION_ICON,
      lang: 'fr',
      data: { url: notification.url },
    }),
  );
});

/** Met au premier plan une fenêtre de l'app sur `path`, ou en ouvre une. */
async function openApp(path) {
  const target = new URL(path, self.location.origin).href;
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  const exact = windows.find((client) => client.url === target);
  if (exact) return exact.focus();
  const appWindow = windows.find((client) => new URL(client.url).origin === self.location.origin);
  if (appWindow) {
    try {
      const navigated = await appWindow.navigate(target);
      return (navigated || appWindow).focus();
    } catch {
      // Fenêtre non contrôlée par ce service worker : nouvelle fenêtre.
    }
  }
  return self.clients.openWindow(target);
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  event.waitUntil(openApp(safeAppPath(data.url) || DEFAULT_NOTIFICATION.url));
});
