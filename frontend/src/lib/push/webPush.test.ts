import { describe, expect, it, vi } from 'vitest';
import type { PushConfig } from '../api/types';
import {
  browserPush,
  decodeApplicationServerKey,
  enablePushNotifications,
  forgetPushOnLogout,
  syncPushSubscription,
  type PushApi,
  type PushBrowser,
} from './webPush';

// Clé publique VAPID factice (65 octets, préfixe 0x04), en base64url.
const KEY_BYTES = Uint8Array.from({ length: 65 }, (_, i) => (i === 0 ? 4 : i));
const KEY = btoa(String.fromCharCode(...KEY_BYTES))
  .replace(/\+/g, '-')
  .replace(/\//g, '_')
  .replace(/=+$/, '');
const OTHER_KEY_BYTES = Uint8Array.from({ length: 65 }, (_, i) => (i === 0 ? 4 : 200 - i));
const CONFIG: PushConfig = { enabled: true, vapidPublicKey: KEY };
const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/appareil';

function fakeSubscription(key: Uint8Array, endpoint = ENDPOINT) {
  return {
    endpoint,
    options: { applicationServerKey: key.buffer },
    toJSON: () => ({ endpoint, expirationTime: null, keys: { p256dh: 'BCle', auth: 'secret' } }),
    unsubscribe: vi.fn(async () => true),
  };
}

function fakeRegistration(existing: ReturnType<typeof fakeSubscription> | null = null) {
  const pushManager = {
    getSubscription: vi.fn(async () => existing),
    subscribe: vi.fn(async (options: { applicationServerKey: Uint8Array }) =>
      fakeSubscription(options.applicationServerKey, `${ENDPOINT}-nouveau`),
    ),
  };
  return { pushManager } as unknown as ServiceWorkerRegistration & {
    pushManager: typeof pushManager;
  };
}

function fakeBrowser(
  overrides: Partial<PushBrowser> & { registration?: () => Promise<unknown> } = {},
): PushBrowser & { requestPermission: ReturnType<typeof vi.fn> } {
  return {
    supported: true,
    needsInstall: false,
    permission: () => 'default',
    requestPermission: vi.fn(async () => 'granted' as NotificationPermission),
    registration: async () => fakeRegistration(),
    ...overrides,
  } as PushBrowser & { requestPermission: ReturnType<typeof vi.fn> };
}

function fakeApi(config: PushConfig = CONFIG) {
  return {
    getPushConfig: vi.fn(async () => config),
    savePushSubscription: vi.fn(async () => undefined),
    deletePushSubscription: vi.fn(async () => undefined),
  } satisfies PushApi;
}

describe('decodeApplicationServerKey', () => {
  it('décode le base64url sans remplissage de la clé VAPID', () => {
    expect([...decodeApplicationServerKey(KEY)]).toEqual([...KEY_BYTES]);
  });
});

describe('enablePushNotifications', () => {
  it("demande la permission, abonne l'appareil et l'enregistre (adresse et clés seulement)", async () => {
    const api = fakeApi();
    const registration = fakeRegistration();
    const browser = fakeBrowser({ registration: async () => registration });

    await expect(enablePushNotifications(api, browser, CONFIG)).resolves.toBe('enabled');

    expect(browser.requestPermission).toHaveBeenCalledOnce();
    const [options] = registration.pushManager.subscribe.mock.calls[0];
    expect(options).toMatchObject({ userVisibleOnly: true });
    expect([...options.applicationServerKey]).toEqual([...KEY_BYTES]);
    expect(api.savePushSubscription).toHaveBeenCalledWith({
      endpoint: `${ENDPOINT}-nouveau`,
      keys: { p256dh: 'BCle', auth: 'secret' },
    });
  });

  it('ne charge rien avant la demande de permission (Safari exige le geste direct)', async () => {
    const api = fakeApi();
    const browser = fakeBrowser();

    await enablePushNotifications(api, browser, CONFIG);

    expect(api.getPushConfig).not.toHaveBeenCalled();
  });

  it.each([
    ['denied', 'denied'],
    ['default', 'dismissed'],
  ] as const)('permission « %s » : rien n’est abonné', async (answer, expected) => {
    const api = fakeApi();
    const registration = fakeRegistration();
    const browser = fakeBrowser({
      requestPermission: vi.fn(async () => answer),
      registration: async () => registration,
    });

    await expect(enablePushNotifications(api, browser, CONFIG)).resolves.toBe(expected);
    expect(registration.pushManager.subscribe).not.toHaveBeenCalled();
    expect(api.savePushSubscription).not.toHaveBeenCalled();
  });

  it('réutilise l’abonnement existant créé avec la même clé', async () => {
    const api = fakeApi();
    const existing = fakeSubscription(KEY_BYTES);
    const registration = fakeRegistration(existing);
    const browser = fakeBrowser({
      permission: () => 'granted',
      registration: async () => registration,
    });

    await enablePushNotifications(api, browser, CONFIG);

    expect(browser.requestPermission).not.toHaveBeenCalled();
    expect(registration.pushManager.subscribe).not.toHaveBeenCalled();
    expect(api.savePushSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ endpoint: ENDPOINT }),
    );
  });

  it('remplace un abonnement créé avec une ancienne clé', async () => {
    const api = fakeApi();
    const stale = fakeSubscription(OTHER_KEY_BYTES);
    const registration = fakeRegistration(stale);
    const browser = fakeBrowser({ registration: async () => registration });

    await enablePushNotifications(api, browser, CONFIG);

    expect(stale.unsubscribe).toHaveBeenCalledOnce();
    expect(registration.pushManager.subscribe).toHaveBeenCalledOnce();
  });

  it('indisponible sans service worker actif (développement) ou push désactivé', async () => {
    await expect(
      enablePushNotifications(
        fakeApi(),
        fakeBrowser({ registration: async () => undefined }),
        CONFIG,
      ),
    ).resolves.toBe('unavailable');
    await expect(
      enablePushNotifications(fakeApi(), fakeBrowser(), { enabled: false, vapidPublicKey: null }),
    ).resolves.toBe('unavailable');
  });
});

describe('syncPushSubscription', () => {
  it('ne demande jamais la permission', async () => {
    const api = fakeApi();
    const browser = fakeBrowser({ permission: () => 'default' });

    await syncPushSubscription(api, browser);

    expect(browser.requestPermission).not.toHaveBeenCalled();
    expect(api.getPushConfig).not.toHaveBeenCalled();
  });

  it("permission déjà accordée : réenregistre l'appareil pour le compte connecté", async () => {
    const api = fakeApi();
    const registration = fakeRegistration(fakeSubscription(KEY_BYTES));
    const browser = fakeBrowser({
      permission: () => 'granted',
      registration: async () => registration,
    });

    await syncPushSubscription(api, browser);

    expect(api.savePushSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ endpoint: ENDPOINT }),
    );
  });
});

describe('forgetPushOnLogout', () => {
  it("fait oublier l'appareil au serveur puis résilie l'abonnement", async () => {
    const api = fakeApi();
    const subscription = fakeSubscription(KEY_BYTES);
    const browser = fakeBrowser({ registration: async () => fakeRegistration(subscription) });

    await forgetPushOnLogout(api, browser);

    expect(api.deletePushSubscription).toHaveBeenCalledWith(ENDPOINT);
    expect(subscription.unsubscribe).toHaveBeenCalledOnce();
  });

  it('ne bloque pas la déconnexion si le serveur ne répond pas', async () => {
    const api = fakeApi();
    api.deletePushSubscription.mockImplementation(() => new Promise(() => undefined));
    const subscription = fakeSubscription(KEY_BYTES);
    const browser = fakeBrowser({ registration: async () => fakeRegistration(subscription) });

    await forgetPushOnLogout(api, browser, 10);

    expect(subscription.unsubscribe).toHaveBeenCalledOnce();
  });

  it('ne lève jamais, même si le navigateur échoue', async () => {
    const browser = fakeBrowser({
      registration: async () => {
        throw new Error('panne');
      },
    });

    await expect(forgetPushOnLogout(fakeApi(), browser)).resolves.toBeUndefined();
  });
});

describe('browserPush', () => {
  it('jsdom (aucun service worker) : non pris en charge, aucun enregistrement', async () => {
    const browser = browserPush(window);

    expect(browser.supported).toBe(false);
    await expect(browser.registration()).resolves.toBeUndefined();
  });
});
