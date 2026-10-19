import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest, UPLOAD_TIMEOUT_MESSAGE, UPLOAD_TIMEOUT_MS } from './http';
import { authStore } from './auth-store';

/**
 * Délais du client HTTP : 10 s pour les appels courts, UPLOAD_TIMEOUT_MS
 * pour les envois de fichiers (la montée d'une photo de téléphone en 4G
 * dépasse souvent 10 s), avec un message dédié quand l'envoi est coupé.
 * Le faux `fetch` respecte le signal d'annulation, comme le vrai.
 */
const NETWORK_MESSAGE = 'Impossible de contacter le serveur. Vérifiez votre connexion.';

function hangingFetch() {
  return vi.fn((_url: string, init: RequestInit) => {
    return new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () =>
        reject(new DOMException('The operation was aborted.', 'AbortError')),
      );
    });
  });
}

function upload() {
  const formData = new FormData();
  formData.set('doc_type', 'cni');
  formData.set('file', new Blob(['x'], { type: 'image/jpeg' }), 'cni.jpg');
  return apiRequest('/artisans/me/documents', { method: 'POST', formData });
}

describe('délais du client HTTP', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    authStore.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('un appel court est coupé à 10 s, avec le message réseau habituel', async () => {
    const fetchMock = hangingFetch();
    vi.stubGlobal('fetch', fetchMock);
    const request = apiRequest('/trades');
    const outcome = expect(request).rejects.toMatchObject({ message: NETWORK_MESSAGE });

    await vi.advanceTimersByTimeAsync(10_000);
    await outcome;
  });

  it("un envoi de fichier n'est PAS coupé à 10 s", async () => {
    const fetchMock = hangingFetch();
    vi.stubGlobal('fetch', fetchMock);
    let settled = false;
    void upload().catch(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(10_000);
    expect(settled).toBe(false);
    const signal = (fetchMock.mock.calls[0][1] as RequestInit).signal as AbortSignal;
    expect(signal.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(UPLOAD_TIMEOUT_MS);
  });

  it('un envoi trop long est coupé à UPLOAD_TIMEOUT_MS, avec un message dédié', async () => {
    vi.stubGlobal('fetch', hangingFetch());
    const outcome = expect(upload()).rejects.toMatchObject({
      code: 'network',
      message: UPLOAD_TIMEOUT_MESSAGE,
    });

    await vi.advanceTimersByTimeAsync(UPLOAD_TIMEOUT_MS);
    await outcome;
  });

  it("un vrai échec réseau pendant un envoi garde le message réseau (ce n'est pas un délai)", async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    await expect(upload()).rejects.toMatchObject({ message: NETWORK_MESSAGE });
  });

  it('une panne du stockage (503) affiche le message du serveur', async () => {
    const message =
      'Le stockage des fichiers est momentanément indisponible, merci de réessayer plus tard.';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: async () => JSON.stringify({ error: { code: 'STOCKAGE_INDISPONIBLE', message } }),
      } as Response),
    );

    await expect(upload()).rejects.toMatchObject({ code: 'network', message });
  });

  it("le délai d'envoi reste raisonnable : plus long que 10 s, borné à quelques minutes", () => {
    expect(UPLOAD_TIMEOUT_MS).toBeGreaterThan(10_000);
    expect(UPLOAD_TIMEOUT_MS).toBeLessThanOrEqual(5 * 60_000);
  });
});
