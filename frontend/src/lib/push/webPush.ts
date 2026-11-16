import type { PushConfig, PushSubscriptionPayload } from '../api/types';
import { isAppleMobile, isRunningStandalone } from '../pwa/installPrompt';

/**
 * Notifications push (Web Push) côté navigateur : un nouveau message
 * s'affiche sur l'appareil, même application fermée (DEPLOYMENT.md §15).
 *
 * - **Jamais imposées** : la permission n'est demandée qu'au clic sur
 *   « Activer » (PushNotificationsPrompt), jamais au chargement.
 * - **Resynchronisées** à chaque ouverture si la permission est déjà
 *   accordée (`syncPushSubscription`) : le serveur connaît toujours
 *   l'abonnement courant de l'appareil, et pour le compte connecté.
 * - **Oubliées à la déconnexion** (`forgetPushOnLogout`) : un appareil
 *   partagé ne reçoit plus rien du compte qui vient de partir.
 * - **iPhone / iPad** : le Web Push n'existe que dans l'app INSTALLÉE
 *   (iOS 16.4+). Dans Safari, on explique comment l'installer.
 *
 * Aucun service worker en développement (src/lib/pwa/serviceWorker.ts) :
 * les notifications ne se testent que sur un build (`npm run preview`).
 */

/** Les appels serveur nécessaires (sous-ensemble de `ApiClient`). */
export interface PushApi {
  getPushConfig(): Promise<PushConfig>;
  savePushSubscription(subscription: PushSubscriptionPayload): Promise<void>;
  deletePushSubscription(endpoint: string): Promise<void>;
}

/** Ce que la logique utilise du navigateur (injectable pour les tests). */
export interface PushBrowser {
  /** Service worker, PushManager et Notification disponibles. */
  readonly supported: boolean;
  /** iPhone/iPad dans Safari : installer l'app d'abord. */
  readonly needsInstall: boolean;
  permission(): NotificationPermission;
  requestPermission(): Promise<NotificationPermission>;
  /** Enregistrement ACTIF du service worker, ou undefined (aucun, ex. en dev). */
  registration(): Promise<ServiceWorkerRegistration | undefined>;
}

/** Délai maximal accordé au serveur pour oublier l'appareil à la déconnexion. */
export const LOGOUT_UNSUBSCRIBE_TIMEOUT_MS = 3000;
/** Attente maximale de l'activation du service worker (sinon : indisponible). */
export const SERVICE_WORKER_READY_TIMEOUT_MS = 10_000;

/** `promise`, ou `fallback` si elle n'aboutit pas dans le délai. */
function withTimeout<T>(promise: Promise<T>, timeoutMs: number, fallback: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    promise,
    new Promise<T>((resolve) => {
      timer = setTimeout(() => resolve(fallback), timeoutMs);
    }),
  ]).finally(() => clearTimeout(timer));
}

export function browserPush(win: Window = window): PushBrowser {
  const container = 'serviceWorker' in win.navigator ? win.navigator.serviceWorker : undefined;
  // `Notification` n'est pas déclaré sur le type `Window` seul (globalThis).
  const notification =
    'Notification' in win ? (win as Window & typeof globalThis).Notification : undefined;
  const supported = Boolean(container && notification && 'PushManager' in win);
  const needsInstall =
    !supported &&
    isAppleMobile(win.navigator.userAgent, win.navigator.maxTouchPoints ?? 0) &&
    !isRunningStandalone(win);
  return {
    supported,
    needsInstall,
    permission: () => notification?.permission ?? 'denied',
    requestPermission: async () => (notification ? notification.requestPermission() : 'denied'),
    registration: async () => {
      if (!container) return undefined;
      // Pas d'attente de `ready` sans enregistrement : elle ne finirait jamais.
      const registration = await container.getRegistration('/');
      if (!registration) return undefined;
      // Un service worker qui ne s'active jamais ne bloque pas l'écran.
      return withTimeout(container.ready, SERVICE_WORKER_READY_TIMEOUT_MS, undefined);
    },
  };
}

/** Clé publique VAPID (base64url) -> octets attendus par `pushManager.subscribe`. */
export function decodeApplicationServerKey(key: string): Uint8Array<ArrayBuffer> {
  const base64 = key.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(base64 + '='.repeat((4 - (base64.length % 4)) % 4));
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function sameKey(subscription: PushSubscription, key: Uint8Array): boolean {
  const current = subscription.options?.applicationServerKey;
  if (!current) return false;
  const bytes = new Uint8Array(current);
  return bytes.length === key.length && bytes.every((byte, i) => byte === key[i]);
}

/**
 * Abonnement de l'appareil pour cette clé : l'actuel s'il a été créé avec
 * la même clé, sinon un nouveau (clé changée côté serveur : l'ancien
 * abonnement ne pourrait plus rien recevoir).
 */
async function deviceSubscription(
  registration: ServiceWorkerRegistration,
  key: Uint8Array<ArrayBuffer>,
): Promise<PushSubscription> {
  const existing = await registration.pushManager.getSubscription();
  if (existing && sameKey(existing, key)) return existing;
  if (existing) await existing.unsubscribe();
  return registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
}

function toPayload(subscription: PushSubscription): PushSubscriptionPayload {
  const json = subscription.toJSON();
  const { p256dh, auth } = json.keys ?? {};
  if (!json.endpoint || !p256dh || !auth) {
    throw new Error('Abonnement push incomplet renvoyé par le navigateur.');
  }
  return { endpoint: json.endpoint, keys: { p256dh, auth } };
}

async function registerDevice(
  api: PushApi,
  browser: PushBrowser,
  config: PushConfig,
): Promise<boolean> {
  if (!config.enabled || !config.vapidPublicKey) return false;
  const registration = await browser.registration();
  if (!registration) return false;
  const subscription = await deviceSubscription(
    registration,
    decodeApplicationServerKey(config.vapidPublicKey),
  );
  await api.savePushSubscription(toPayload(subscription));
  return true;
}

export type EnablePushResult = 'enabled' | 'denied' | 'dismissed' | 'unavailable';

/**
 * Clic sur « Activer » : demande la permission PUIS abonne l'appareil.
 * `config` est déjà chargée : la permission est demandée sans attente
 * réseau préalable (Safari exige qu'elle suive directement le geste).
 * Lève en cas d'échec technique (l'écran affiche alors une erreur).
 */
export async function enablePushNotifications(
  api: PushApi,
  browser: PushBrowser,
  config: PushConfig,
): Promise<EnablePushResult> {
  if (!browser.supported || !config.enabled) return 'unavailable';
  const permission =
    browser.permission() === 'granted' ? 'granted' : await browser.requestPermission();
  if (permission === 'denied') return 'denied';
  if (permission !== 'granted') return 'dismissed';
  return (await registerDevice(api, browser, config)) ? 'enabled' : 'unavailable';
}

/**
 * À l'ouverture de l'app (compte connecté) : si la permission est déjà
 * accordée, (ré)enregistre l'abonnement de l'appareil pour ce compte.
 * Ne demande JAMAIS la permission.
 */
export async function syncPushSubscription(api: PushApi, browser: PushBrowser): Promise<void> {
  if (!browser.supported || browser.permission() !== 'granted') return;
  await registerDevice(api, browser, await api.getPushConfig());
}

/**
 * À la déconnexion, AVANT d'effacer la session : le serveur oublie
 * l'appareil (délai borné), puis l'abonnement du navigateur est résilié.
 * Ne lève jamais : la déconnexion ne doit pas en dépendre.
 */
export async function forgetPushOnLogout(
  api: PushApi,
  browser: PushBrowser,
  timeoutMs = LOGOUT_UNSUBSCRIBE_TIMEOUT_MS,
): Promise<void> {
  try {
    if (!browser.supported) return;
    const registration = await browser.registration();
    const subscription = await registration?.pushManager.getSubscription();
    if (!subscription) return;
    await withTimeout(
      api.deletePushSubscription(subscription.endpoint).catch(() => undefined),
      timeoutMs,
      undefined,
    );
    // Même si le serveur n'a pas répondu : l'abonnement résilié ici, le
    // service de push répondra « expiré » et le serveur le supprimera.
    await subscription.unsubscribe();
  } catch {
    // Best-effort : rien ne doit empêcher la déconnexion.
  }
}
