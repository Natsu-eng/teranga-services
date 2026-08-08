import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from './AuthProvider';
import { useAuth } from './hooks/useAuth';
import { authStore } from '../../lib/api/auth-store';

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  } as Response;
}

const backendUser = {
  id: 'u1',
  phone: '+221771234501',
  full_name: 'Diandé Diallo',
  role: 'client',
  locale: 'fr',
  phone_verified_at: '2026-01-01T00:00:00Z',
  artisan_profile_id: null,
};

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(auth.isLoading)}</span>
      <span data-testid="authenticated">{String(auth.isAuthenticated)}</span>
      <span data-testid="role">{auth.role ?? 'none'}</span>
      <span data-testid="name">{auth.user?.fullName ?? ''}</span>
      <button onClick={() => void auth.requestOtp('+221771234501')}>request</button>
      <button onClick={() => void auth.login('+221771234501', '123456')}>login</button>
      <button onClick={() => void auth.signup('+221771234501', '123456', 'artisan', 'Idrissa Diop')}>
        signup
      </button>
      <button onClick={() => void auth.updateFullName('Nouveau Nom')}>updateFullName</button>
      <button onClick={() => void auth.logout()}>logout</button>
    </div>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    authStore.clear();
    authStore.onForcedLogout(null);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('starts signed out with no refresh token, without calling the backend', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));
    expect(screen.getByTestId('authenticated').textContent).toBe('false');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('establishes a session through requestOtp -> login (verify-otp), role coming from the backend', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/request-otp')) return Promise.resolve(jsonResponse(204, undefined));
      if (url.endsWith('/auth/verify-otp')) {
        return Promise.resolve(
          jsonResponse(200, { access: 'access-1', refresh: 'refresh-1', user: backendUser }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));

    fireEvent.click(screen.getByText('request'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/request-otp', expect.anything()));

    fireEvent.click(screen.getByText('login'));

    await waitFor(() => expect(screen.getByTestId('authenticated').textContent).toBe('true'));
    expect(screen.getByTestId('role').textContent).toBe('client');
    expect(screen.getByTestId('name').textContent).toBe('Diandé Diallo');
    expect(authStore.getAccessToken()).toBe('access-1');
    expect(authStore.getRefreshToken()).toBe('refresh-1');

    const verifyCall = fetchMock.mock.calls.find(([url]) => (url as string).endsWith('/auth/verify-otp'));
    expect(verifyCall?.[1]?.body).toBe(
      JSON.stringify({ phone: '+221771234501', code: '123456', intent: 'login' }),
    );
  });

  it('establishes a session through signup (verify-otp with intent=signup and the chosen role)', async () => {
    const artisanUser = { ...backendUser, role: 'artisan' };
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/verify-otp')) {
        return Promise.resolve(
          jsonResponse(200, { access: 'access-2', refresh: 'refresh-2', user: artisanUser }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));

    fireEvent.click(screen.getByText('signup'));

    await waitFor(() => expect(screen.getByTestId('authenticated').textContent).toBe('true'));
    expect(screen.getByTestId('role').textContent).toBe('artisan');

    const verifyCall = fetchMock.mock.calls.find(([url]) => (url as string).endsWith('/auth/verify-otp'));
    expect(verifyCall?.[1]?.body).toBe(
      JSON.stringify({
        phone: '+221771234501',
        code: '123456',
        intent: 'signup',
        role: 'artisan',
        full_name: 'Idrissa Diop',
      }),
    );
  });

  it('updates the current name through updateFullName (PATCH /users/me)', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/verify-otp')) {
        return Promise.resolve(
          jsonResponse(200, { access: 'access-1', refresh: 'refresh-1', user: backendUser }),
        );
      }
      if (url.endsWith('/users/me')) {
        return Promise.resolve(jsonResponse(200, { ...backendUser, full_name: 'Nouveau Nom' }));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));

    fireEvent.click(screen.getByText('login'));
    await waitFor(() => expect(screen.getByTestId('authenticated').textContent).toBe('true'));

    fireEvent.click(screen.getByText('updateFullName'));

    await waitFor(() => expect(screen.getByTestId('name').textContent).toBe('Nouveau Nom'));

    const patchCall = fetchMock.mock.calls.find(([url]) => (url as string).endsWith('/users/me'));
    expect(patchCall?.[1]?.method).toBe('PATCH');
    expect(patchCall?.[1]?.body).toBe(JSON.stringify({ full_name: 'Nouveau Nom' }));
  });

  it('restores the session on mount from a persisted refresh token (silent refresh via GET /auth/me)', async () => {
    authStore.setTokens({ access: '', refresh: 'persisted-refresh' });

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/me')) {
        // No access token yet in this fresh page load -> 401 once, then the
        // http client's own refresh dance retries after /auth/refresh.
        return authStore.getAccessToken() === 'fresh-access'
          ? Promise.resolve(jsonResponse(200, backendUser))
          : Promise.resolve(jsonResponse(401, { error: { code: 'TOKEN_INVALIDE', message: 'x' } }));
      }
      if (url.endsWith('/auth/refresh')) {
        return Promise.resolve(jsonResponse(200, { access: 'fresh-access', refresh: 'fresh-refresh' }));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));
    expect(screen.getByTestId('authenticated').textContent).toBe('true');
    expect(screen.getByTestId('name').textContent).toBe('Diandé Diallo');
  });

  it('clears the session when notified of a forced logout (failed refresh elsewhere)', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/verify-otp')) {
        return Promise.resolve(
          jsonResponse(200, { access: 'access-1', refresh: 'refresh-1', user: backendUser }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));

    fireEvent.click(screen.getByText('login'));
    await waitFor(() => expect(screen.getByTestId('authenticated').textContent).toBe('true'));

    authStore.notifyForcedLogout();

    await waitFor(() => expect(screen.getByTestId('authenticated').textContent).toBe('false'));
    expect(screen.getByTestId('role').textContent).toBe('none');
  });
});
