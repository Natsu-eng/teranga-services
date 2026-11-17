import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { api } from '../../lib/api';
import type { PushBrowser } from '../../lib/push/webPush';
import { syncPushSubscription } from '../../lib/push/webPush';
import type { AuthContextValue } from '../auth/auth-context';
import { useAuth } from '../auth/hooks/useAuth';
import { PushSubscriptionSync } from './PushSubscriptionSync';

vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/push/webPush', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/push/webPush')>();
  return { ...actual, syncPushSubscription: vi.fn() };
});

const mockedUseAuth = vi.mocked(useAuth);
const mockedSync = vi.mocked(syncPushSubscription);

const push: PushBrowser = {
  supported: true,
  needsInstall: false,
  permission: () => 'granted',
  requestPermission: vi.fn(),
  registration: vi.fn(),
};

function auth(role: 'client' | 'artisan' | 'admin' | null, id = 'u1'): AuthContextValue {
  return {
    user: role
      ? {
          id,
          phone: '+221770000000',
          fullName: 'Awa Diop',
          role,
          locale: 'fr',
          phoneVerifiedAt: null,
          artisanProfileId: null,
        }
      : null,
    role,
    isAuthenticated: role !== null,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
  };
}

describe('PushSubscriptionSync', () => {
  beforeEach(() => {
    mockedSync.mockReset();
    // Implémentation explicite plutôt que `mockResolvedValue` : avec Vitest 4,
    // un rejet programmé ensuite serait signalé même une fois intercepté.
    mockedSync.mockImplementation(async () => undefined);
  });
  afterEach(cleanup);

  it.each(['client', 'artisan'] as const)(
    'compte %s : resynchronise une fois par session',
    (role) => {
      mockedUseAuth.mockReturnValue(auth(role));
      const { rerender } = render(<PushSubscriptionSync browser={push} />);
      rerender(<PushSubscriptionSync browser={push} />);

      expect(mockedSync).toHaveBeenCalledOnce();
      expect(mockedSync).toHaveBeenCalledWith(api, push);
    },
  );

  it('changement de compte : resynchronise pour le nouveau', () => {
    mockedUseAuth.mockReturnValue(auth('client', 'u1'));
    const { rerender } = render(<PushSubscriptionSync browser={push} />);
    mockedUseAuth.mockReturnValue(auth('artisan', 'u2'));
    rerender(<PushSubscriptionSync browser={push} />);

    expect(mockedSync).toHaveBeenCalledTimes(2);
  });

  it.each([null, 'admin'] as const)('visiteur ou admin (%s) : rien', (role) => {
    mockedUseAuth.mockReturnValue(auth(role));
    render(<PushSubscriptionSync browser={push} />);

    expect(mockedSync).not.toHaveBeenCalled();
  });

  it('un échec reste silencieux pour l’écran (simple avertissement)', async () => {
    const warnings: unknown[][] = [];
    const warn = vi.spyOn(console, 'warn').mockImplementation((...args: unknown[]) => {
      warnings.push(args);
    });
    mockedSync.mockImplementation(() => Promise.reject(new TypeError('panne réseau')));
    mockedUseAuth.mockReturnValue(auth('client'));

    const { container } = render(<PushSubscriptionSync browser={push} />);

    await vi.waitFor(() => expect(warnings).toHaveLength(1));
    expect(String(warnings[0][0])).toContain('abonnement non resynchronisé');
    expect(container).toBeEmptyDOMElement();
    warn.mockRestore();
  });
});
