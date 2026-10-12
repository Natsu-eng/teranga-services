import { afterEach, describe, expect, it, vi } from 'vitest';
import { httpApiClient } from './http-impl';

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response;
}

/** Remplace `fetch` et renvoie l'espion, pour inspecter URL, méthode et corps. */
function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(status, body));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { url, init };
}

const emptyPage = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } };

const backendUser = {
  id: 'u1',
  full_name: 'Awa Diop',
  phone: '+221770000001',
  role: 'admin',
  created_at: '2026-01-01T10:00:00Z',
  has_artisan_profile: false,
  is_self: false,
  can_grant_admin: false,
  can_revoke_admin: false,
  guard: 'Dernier administrateur : il ne peut pas être retiré.',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('back-office HTTP', () => {
  it('liste les comptes avec recherche nettoyée et rôle, et mappe les garde-fous', async () => {
    const fetchMock = stubFetch({
      items: [backendUser],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });

    const page = await httpApiClient.listAdminUsers({ role: 'admin', q: '  Awa  ' });

    expect(lastCall(fetchMock).url).toMatch(/\/admin\/users\?role=admin&q=Awa$/);
    expect(page).toEqual({
      items: [
        {
          id: 'u1',
          fullName: 'Awa Diop',
          phone: '+221770000001',
          role: 'admin',
          createdAt: '2026-01-01T10:00:00Z',
          hasArtisanProfile: false,
          isSelf: false,
          canGrantAdmin: false,
          canRevokeAdmin: false,
          guard: 'Dernier administrateur : il ne peut pas être retiré.',
        },
      ],
      page: 1,
      total: 1,
      totalPages: 1,
    });
  });

  it('retire le rôle par POST, une note vide part à null', async () => {
    const fetchMock = stubFetch({ ...backendUser, role: 'client' });

    await httpApiClient.revokeAdmin('u1', '');

    const { url, init } = lastCall(fetchMock);
    expect(url).toMatch(/\/admin\/users\/u1\/revoke-admin$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ note: null });
  });

  it('ajoute un taux en snake_case, sans jamais de palier', async () => {
    const fetchMock = stubFetch({
      id: 'r1',
      rate_bps: 1250,
      trade_code: 'plomberie',
      trade_label: 'Plomberie',
      effective_from: '2026-11-01T00:00:00Z',
      effective_to: null,
      state: 'programme',
      interventions_count: 0,
      created_at: '2026-10-12T10:00:00Z',
    });

    const rate = await httpApiClient.addCommissionRate({
      rateBps: 1250,
      tradeCode: 'plomberie',
      effectiveFrom: '2026-11-01T00:00:00.000Z',
      note: 'Grille 2027',
    });

    const { url, init } = lastCall(fetchMock);
    expect(url).toMatch(/\/admin\/commission-rates$/);
    expect(JSON.parse(String(init.body))).toEqual({
      rate_bps: 1250,
      trade_code: 'plomberie',
      effective_from: '2026-11-01T00:00:00.000Z',
      note: 'Grille 2027',
    });
    expect(rate.state).toBe('programme');
    expect(rate.interventionsCount).toBe(0);
  });

  it('filtre le journal par type de cible', async () => {
    const fetchMock = stubFetch(emptyPage);

    await httpApiClient.listAuditEntries({ targetType: 'commission_rate', page: 2 });

    expect(lastCall(fetchMock).url).toMatch(/\/admin\/audit\?target_type=commission_rate&page=2$/);
  });

  it('signale un avis reçu (espace Pro) et mappe son statut de modération', async () => {
    const fetchMock = stubFetch({
      id: 'rev-1',
      rating: 2,
      comment: 'Moyen.',
      author_name: 'Awa D.',
      created_at: '2026-01-01T10:00:00Z',
      status: 'signale',
      report_reason: 'Avis mensonger, jamais venu.',
      reported_at: '2026-10-12T10:00:00Z',
      can_report: false,
    });

    const review = await httpApiClient.reportReview('rev-1', 'Avis mensonger, jamais venu.');

    const { url, init } = lastCall(fetchMock);
    expect(url).toMatch(/\/artisans\/me\/reviews\/rev-1\/report$/);
    expect(JSON.parse(String(init.body))).toEqual({ reason: 'Avis mensonger, jamais venu.' });
    expect(review).toMatchObject({ status: 'signale', canReport: false });
  });
});
