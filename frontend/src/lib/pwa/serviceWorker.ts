/**
 * Enregistrement du service worker de l'application installable (modèle :
 * pwa/sw.js, produit au build en /sw.js).
 *
 * - Build de production : enregistrement à la racine. `updateViaCache:
 *   'none'` : le navigateur revérifie sw.js sur le réseau à chaque
 *   navigation, sans passer par son cache HTTP (mise à jour jamais retardée).
 * - Développement : AUCUN service worker. Si un build de production a déjà
 *   été servi sur la même origine (ex. `vite preview` sur le port 3000), son
 *   service worker et ses caches sont retirés : le serveur de développement
 *   ne doit jamais être masqué par une ancienne version en cache.
 */

export const SERVICE_WORKER_URL = '/sw.js';
// Préfixe des caches créés par pwa/sw.js (CACHE_PREFIX) : seuls ceux-là sont purgés.
const SHELL_CACHE_PREFIX = 'teranga-shell-';

export async function syncServiceWorker(
  isProduction: boolean,
  container: ServiceWorkerContainer | undefined,
  cacheStorage: CacheStorage | undefined,
): Promise<void> {
  // Contexte non sécurisé (http hors localhost) ou navigateur ancien : rien à faire.
  if (!container) return;

  if (isProduction) {
    await container.register(SERVICE_WORKER_URL, { scope: '/', updateViaCache: 'none' });
    return;
  }

  const registrations = await container.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));
  if (cacheStorage) {
    const keys = await cacheStorage.keys();
    await Promise.all(
      keys
        .filter((key) => key.startsWith(SHELL_CACHE_PREFIX))
        .map((key) => cacheStorage.delete(key)),
    );
  }
}

/** Branche la synchronisation au chargement de la page (après le rendu initial). */
export function setupServiceWorker(win: Window = window): void {
  const container = 'serviceWorker' in win.navigator ? win.navigator.serviceWorker : undefined;
  const cacheStorage = 'caches' in win ? win.caches : undefined;
  win.addEventListener('load', () => {
    syncServiceWorker(import.meta.env.PROD, container, cacheStorage).catch((error: unknown) => {
      // Jamais bloquant : sans service worker, l'app fonctionne normalement
      // (en ligne), elle n'est simplement pas disponible hors connexion.
      console.warn(
        "Service worker non enregistré : l'application reste utilisable en ligne.",
        error,
      );
    });
  });
}
