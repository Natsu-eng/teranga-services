import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { TestEnvironmentBanner } from './TestEnvironmentBanner';
import type { InstanceMeta } from '../../lib/api/instance-meta';
import { fetchInstanceMeta } from '../../lib/api/instance-meta';
import { authStore } from '../../lib/api/auth-store';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  authStore.clear();
});

const BANNER_TEXT = /Version de test/;

function meta(environment: InstanceMeta['environment']): () => Promise<InstanceMeta> {
  return () => Promise.resolve({ environment, otp_test_mode: environment === 'staging' });
}

/** Laisse la promesse de chargement se résoudre (ou échouer). */
async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('bandeau « Version de test »', () => {
  it.each(['staging', 'development', 'test'] as const)('visible en %s', async (environment) => {
    render(<TestEnvironmentBanner loadMeta={meta(environment)} />);

    const banner = await screen.findByRole('note');
    expect(banner).toHaveTextContent(BANNER_TEXT);
    expect(banner).toHaveAttribute('data-environment', environment);
  });

  it('absent en production', async () => {
    render(<TestEnvironmentBanner loadMeta={meta('production')} />);
    await settle();

    expect(screen.queryByText(BANNER_TEXT)).toBeNull();
  });

  it('absent tant que le backend n’a pas répondu', () => {
    render(<TestEnvironmentBanner loadMeta={() => new Promise(() => {})} />);

    expect(screen.queryByText(BANNER_TEXT)).toBeNull();
  });

  it('absent si le backend est injoignable (jamais affiché par défaut)', async () => {
    render(<TestEnvironmentBanner loadMeta={() => Promise.reject(new Error('réseau'))} />);
    await settle();

    expect(screen.queryByText(BANNER_TEXT)).toBeNull();
  });
});

describe('GET /api/v1/meta', () => {
  it('appelle /meta sans jeton, même connecté', async () => {
    authStore.setTokens({ access: 'jeton-secret', refresh: 'r' });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ environment: 'staging', otp_test_mode: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchInstanceMeta()).resolves.toEqual({
      environment: 'staging',
      otp_test_mode: true,
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/meta$/);
    expect(init.headers).not.toHaveProperty('Authorization');
  });
});
