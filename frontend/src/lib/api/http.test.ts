import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from './http';
import { authStore } from './auth-store';
import { ApiError } from './types';

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  } as Response;
}

describe('http client', () => {
  beforeEach(() => {
    authStore.clear();
    authStore.onForcedLogout(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('resolves with the parsed JSON body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { hello: 'world' })));

    const result = await apiRequest<{ hello: string }>('/trades');
    expect(result).toEqual({ hello: 'world' });
  });

  it('maps a backend { error: { code, message } } body to ApiError, using the message as-is', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(404, { error: { code: 'ARTISAN_NOT_FOUND', message: 'Artisan introuvable.' } }),
      ),
    );

    const promise = apiRequest('/artisans/does-not-exist');
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({ code: 'not_found', message: 'Artisan introuvable.' });
  });

  it('maps a 4xx business error to the validation code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(400, { error: { code: 'OTP_INVALIDE', message: 'Code invalide.' } })),
    );

    const promise = apiRequest('/auth/verify-otp', { method: 'POST', body: {}, skipAuth: true });
    await expect(promise).rejects.toMatchObject({ code: 'validation', message: 'Code invalide.' });
  });

  it('falls back to a generic French message when the error body is missing/malformed', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => '' } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const promise = apiRequest('/trades');
    await expect(promise).rejects.toMatchObject({ code: 'network' });
  });

  it('injects the Authorization header when an access token is set', async () => {
    authStore.setTokens({ access: 'access-123', refresh: 'refresh-123' });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/artisans');

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer access-123');
  });

  it('does not inject Authorization when skipAuth is set, even with a token present', async () => {
    authStore.setTokens({ access: 'access-123', refresh: 'refresh-123' });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(204, undefined));
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/auth/request-otp', { method: 'POST', body: { phone: '+221771234501' }, skipAuth: true });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('refreshes once on a 401, then retries the original request with the new token', async () => {
    authStore.setTokens({ access: 'stale-access', refresh: 'refresh-123' });
    const fetchMock = vi.fn();
    let call = 0;
    fetchMock.mockImplementation((url: string) => {
      call += 1;
      if (url.endsWith('/artisans') && call === 1) return Promise.resolve(jsonResponse(401, { error: { code: 'TOKEN_INVALIDE', message: 'Session invalide.' } }));
      if (url.endsWith('/auth/refresh')) return Promise.resolve(jsonResponse(200, { access: 'fresh-access', refresh: 'fresh-refresh' }));
      if (url.endsWith('/artisans')) return Promise.resolve(jsonResponse(200, [{ id: 'a1' }]));
      throw new Error(`unexpected call: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await apiRequest('/artisans');

    expect(result).toEqual([{ id: 'a1' }]);
    expect(fetchMock).toHaveBeenCalledTimes(3); // 401, refresh, retry
    expect(authStore.getAccessToken()).toBe('fresh-access');
    const retryInit = fetchMock.mock.calls[2][1] as RequestInit;
    expect((retryInit.headers as Record<string, string>).Authorization).toBe('Bearer fresh-access');
  });

  it('triggers exactly one refresh call for several concurrent 401s', async () => {
    authStore.setTokens({ access: 'stale-access', refresh: 'refresh-123' });
    let refreshCalls = 0;
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1;
        return Promise.resolve(jsonResponse(200, { access: 'fresh-access', refresh: 'fresh-refresh' }));
      }
      // Every non-refresh call 401s until the token has been refreshed.
      if (authStore.getAccessToken() === 'fresh-access') return Promise.resolve(jsonResponse(200, []));
      return Promise.resolve(jsonResponse(401, { error: { code: 'TOKEN_INVALIDE', message: 'Session invalide.' } }));
    });
    vi.stubGlobal('fetch', fetchMock);

    await Promise.all([apiRequest('/artisans'), apiRequest('/trades'), apiRequest('/artisans/1/reviews')]);

    expect(refreshCalls).toBe(1);
  });

  it('clears the session and notifies a forced logout when the refresh itself fails', async () => {
    authStore.setTokens({ access: 'stale-access', refresh: 'refresh-123' });
    const forcedLogout = vi.fn();
    authStore.onForcedLogout(forcedLogout);

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/refresh')) {
        return Promise.resolve(jsonResponse(401, { error: { code: 'REFRESH_INVALIDE', message: 'Session invalide ou expirée.' } }));
      }
      return Promise.resolve(jsonResponse(401, { error: { code: 'TOKEN_INVALIDE', message: 'Session invalide.' } }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const promise = apiRequest('/artisans');
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({ code: 'validation' });

    expect(authStore.getAccessToken()).toBeNull();
    expect(authStore.getRefreshToken()).toBeNull();
    expect(forcedLogout).toHaveBeenCalledTimes(1);
  });

  it('rejects with a network ApiError without a refresh token to try', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, { error: { code: 'TOKEN_INVALIDE', message: 'x' } }));
    vi.stubGlobal('fetch', fetchMock);

    const promise = apiRequest('/artisans');
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    // No refresh token in the store at all: performRefresh short-circuits without calling fetch again.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
