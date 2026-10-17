import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import {
  captureInstallPrompt,
  isAppleMobile,
  isRunningStandalone,
  resetInstallPromptForTests,
} from './installPrompt';
import { SERVICE_WORKER_URL, syncServiceWorker } from './serviceWorker';
import {
  INSTALL_HINT_DISMISSED_KEY,
  InstallAppHint,
} from '../../features/profile/components/InstallAppHint';

const ANDROID_UA =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36';
const IPHONE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const IPAD_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15';

// --------------------------------------------------- service worker

describe('enregistrement du service worker', () => {
  function fakeContainer(registrations: { unregister: () => Promise<boolean> }[] = []) {
    return {
      register: vi.fn().mockResolvedValue({}),
      getRegistrations: vi.fn().mockResolvedValue(registrations),
    } as unknown as ServiceWorkerContainer & {
      register: ReturnType<typeof vi.fn>;
      getRegistrations: ReturnType<typeof vi.fn>;
    };
  }

  it('production : enregistre /sw.js à la racine, sans cache HTTP pour les mises à jour', async () => {
    const container = fakeContainer();
    await syncServiceWorker(true, container, undefined);

    expect(container.register).toHaveBeenCalledWith(SERVICE_WORKER_URL, {
      scope: '/',
      updateViaCache: 'none',
    });
  });

  it('développement : aucun enregistrement, et un ancien service worker est retiré avec ses caches', async () => {
    const old = { unregister: vi.fn().mockResolvedValue(true) };
    const container = fakeContainer([old]);
    const cacheStorage = {
      keys: vi.fn().mockResolvedValue(['teranga-shell-abc', 'autre-usage']),
      delete: vi.fn().mockResolvedValue(true),
    } as unknown as CacheStorage & { delete: ReturnType<typeof vi.fn> };

    await syncServiceWorker(false, container, cacheStorage);

    expect(container.register).not.toHaveBeenCalled();
    expect(old.unregister).toHaveBeenCalledOnce();
    expect(cacheStorage.delete).toHaveBeenCalledExactlyOnceWith('teranga-shell-abc');
  });

  it('sans support (contexte non sécurisé) : ne fait rien', async () => {
    await expect(syncServiceWorker(true, undefined, undefined)).resolves.toBeUndefined();
  });
});

// --------------------------------------------------- détection de plateforme

describe('détection de plateforme', () => {
  it('reconnaît iPhone et iPad (iPadOS se présente comme un Mac tactile)', () => {
    expect(isAppleMobile(IPHONE_UA, 5)).toBe(true);
    expect(isAppleMobile(IPAD_UA, 5)).toBe(true);
    expect(isAppleMobile(IPAD_UA, 0)).toBe(false); // vrai Mac
    expect(isAppleMobile(ANDROID_UA, 5)).toBe(false);
  });

  it('reconnaît une app déjà installée (Android ou iOS)', () => {
    const win = (standalone: boolean, iosStandalone?: boolean) =>
      ({
        matchMedia: () => ({ matches: standalone }),
        navigator: { standalone: iosStandalone },
      }) as unknown as Window;
    expect(isRunningStandalone(win(true))).toBe(true);
    expect(isRunningStandalone(win(false, true))).toBe(true);
    expect(isRunningStandalone(win(false))).toBe(false);
    // jsdom : pas de matchMedia, jamais d'erreur.
    expect(isRunningStandalone({ navigator: {} } as unknown as Window)).toBe(false);
  });
});

// --------------------------------------------------- conseil « Installer l'app »

describe('conseil « Installer l’app »', () => {
  let userAgent: string;

  beforeEach(() => {
    userAgent = ANDROID_UA;
    vi.spyOn(window.navigator, 'userAgent', 'get').mockImplementation(() => userAgent);
    window.localStorage.clear();
    resetInstallPromptForTests();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    resetInstallPromptForTests();
  });

  /** Simule l'événement Chrome « l'app est installable ». */
  function fireInstallable(outcome: 'accepted' | 'dismissed' = 'accepted') {
    const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
      prompt: ReturnType<typeof vi.fn>;
      userChoice: Promise<{ outcome: string }>;
    };
    event.prompt = vi.fn().mockResolvedValue(undefined);
    event.userChoice = Promise.resolve({ outcome });
    act(() => {
      window.dispatchEvent(event);
    });
    return event;
  }

  // Une seule capture pour tout le fichier : comme au démarrage de l'app.
  captureInstallPrompt(window);

  it('rien tant que le navigateur ne propose pas l’installation (ni iPhone)', () => {
    render(<InstallAppHint />);
    expect(screen.queryByText("Installer l'app")).toBeNull();
  });

  it('Android : bouton qui ouvre la boîte d’installation du navigateur', () => {
    render(<InstallAppHint />);
    const event = fireInstallable();

    // La mini-bannière automatique est évitée : l'invitation reste discrète.
    expect(event.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Installer' }));

    expect(event.prompt).toHaveBeenCalledOnce();
    // Un événement ne sert qu'une fois : le bouton disparaît.
    expect(screen.queryByRole('button', { name: 'Installer' })).toBeNull();
  });

  it('iPhone : explique le geste Safari « Sur l’écran d’accueil »', () => {
    userAgent = IPHONE_UA;
    render(<InstallAppHint />);

    expect(screen.getByText("Installer l'app")).toBeInTheDocument();
    expect(screen.getByText(/Sur l'écran d'accueil/)).toBeInTheDocument();
  });

  it('masquable, et le reste après rechargement', () => {
    userAgent = IPHONE_UA;
    const { unmount } = render(<InstallAppHint />);
    fireEvent.click(screen.getByRole('button', { name: 'Masquer ce conseil' }));

    expect(screen.queryByText("Installer l'app")).toBeNull();
    expect(window.localStorage.getItem(INSTALL_HINT_DISMISSED_KEY)).toBe('1');
    unmount();
    render(<InstallAppHint />);
    expect(screen.queryByText("Installer l'app")).toBeNull();
  });

  it('rien quand l’app est déjà ouverte installée', () => {
    userAgent = IPHONE_UA;
    Object.defineProperty(window.navigator, 'standalone', { value: true, configurable: true });
    try {
      render(<InstallAppHint />);
      expect(screen.queryByText("Installer l'app")).toBeNull();
    } finally {
      Object.defineProperty(window.navigator, 'standalone', {
        value: undefined,
        configurable: true,
      });
    }
  });

  it('l’installation terminée retire l’invitation', () => {
    render(<InstallAppHint />);
    fireInstallable();
    expect(screen.getByRole('button', { name: 'Installer' })).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(new Event('appinstalled'));
    });
    expect(screen.queryByRole('button', { name: 'Installer' })).toBeNull();
  });
});
