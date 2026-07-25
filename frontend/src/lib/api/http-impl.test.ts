import { afterEach, describe, expect, it, vi } from 'vitest';
import { httpApiClient } from './http-impl';
import { ApiError } from './types';

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response;
}

const backendArtisan = {
  id: 'a1',
  full_name: 'Idrissa Diop',
  avatar_url: '/images/idrissa.jpg',
  bio: 'Plombier expérimenté.',
  years_experience: 8,
  is_available: true,
  verified_status: 'verified',
  rating_avg: 4.9,
  review_count: 2,
  distance_m: 1200,
  trades: [
    {
      trade: { id: 't1', code: 'plomberie', label_fr: 'Plomberie' },
      hourly_rate_fcfa: 15000,
      service_radius_m: 5000,
      has_custom_service_area: false,
    },
  ],
};

describe('httpApiClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('listArtisans', () => {
    it('maps the backend page envelope into a flat Artisan[] with neutral placeholders for uncovered fields', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [backendArtisan],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const artisans = await httpApiClient.listArtisans!();

      expect(artisans).toHaveLength(1);
      const artisan = artisans[0];
      expect(artisan.id).toBe('a1');
      expect(artisan.name).toBe('Idrissa Diop');
      expect(artisan.trade).toBe('Plomberie');
      expect(artisan.verified).toBe(true);
      expect(artisan.distance).toBe('1.2 km');
      // No public price/contact/location exposed by the backend -> neutral copy, never invented data.
      expect(artisan.priceBase).toBe('Tarif sur devis');
      expect(artisan.coverUrl).toBeNull();
      expect(artisan.realisations).toEqual([]);
    });

    it('maps a null rating_avg (no published review yet) to 0, not a crash', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [{ ...backendArtisan, rating_avg: null, review_count: 0 }],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const [artisan] = await httpApiClient.listArtisans!();
      expect(artisan.rating).toBe(0);
    });

    it('leaves distance blank when distance_m is null (no `near` supplied)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [{ ...backendArtisan, distance_m: null }],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const [artisan] = await httpApiClient.listArtisans!();
      expect(artisan.distance).toBe('');
    });

    it('builds the query string from filters (trade code, near, sort, pagination)', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } }));
      vi.stubGlobal('fetch', fetchMock);

      await httpApiClient.listArtisans!({
        trade: 'plomberie',
        near: { lat: 14.7, lng: -17.4 },
        radiusM: 5000,
        sort: 'distance',
        page: 2,
        pageSize: 10,
      });

      const [url] = fetchMock.mock.calls[0] as [string];
      expect(url).toContain('/api/v1/artisans?');
      expect(url).toContain('trade=plomberie');
      expect(url).toContain('near=14.7%2C-17.4');
      expect(url).toContain('radius_m=5000');
      expect(url).toContain('sort=distance');
      expect(url).toContain('page=2');
      expect(url).toContain('page_size=10');
    });
  });

  describe('getArtisanById', () => {
    it('merges the detail endpoint with its reviews into a single Artisan', async () => {
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/reviews')) {
          return Promise.resolve(
            jsonResponse(200, {
              items: [
                {
                  id: 'r1',
                  rating: 5,
                  comment: 'Excellent travail.',
                  author_name: 'Fatou Kane',
                  created_at: new Date().toISOString(),
                },
              ],
              pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
            }),
          );
        }
        return Promise.resolve(jsonResponse(200, { ...backendArtisan, cover_url: '/images/cover.jpg' }));
      });
      vi.stubGlobal('fetch', fetchMock);

      const artisan = await httpApiClient.getArtisanById!('a1');

      expect(artisan.coverUrl).toBe('/images/cover.jpg');
      expect(artisan.reviews).toHaveLength(1);
      expect(artisan.reviews[0]).toMatchObject({ author: 'Fatou Kane', rating: 5, avatarInitials: 'FK' });
    });

    it('propagates the backend 404 message as-is (already French, display-ready)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(jsonResponse(404, { error: { code: 'ARTISAN_NOT_FOUND', message: 'Artisan introuvable.' } })),
      );

      const promise = httpApiClient.getArtisanById!('does-not-exist');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: 'not_found', message: 'Artisan introuvable.' });
    });
  });

  describe('listTrades', () => {
    it('maps the backend trade reference list', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, [{ id: 't1', code: 'plomberie', label_fr: 'Plomberie' }]),
        ),
      );

      const trades = await httpApiClient.listTrades!();
      expect(trades).toEqual([{ id: 't1', code: 'plomberie', labelFr: 'Plomberie' }]);
    });
  });

  describe('analyzeProblem', () => {
    const backendTriageResult = {
      trade_code: 'plomberie',
      price_min_fcfa: 8000,
      price_max_fcfa: 15000,
      urgency: 'normal' as const,
      suggested_quote: { labor_fcfa: 8000, materials_fcfa: 4000, total_fcfa: 12000 },
    };
    const backendTrades = [
      { id: 't1', code: 'plomberie', label_fr: 'Plomberie' },
      { id: 't2', code: 'electricite', label_fr: 'Électricité' },
    ];

    it('posts the description to /ai/analyze and maps the TriageResult into an AIAnalysisResult', async () => {
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/ai/analyze')) return Promise.resolve(jsonResponse(200, backendTriageResult));
        return Promise.resolve(jsonResponse(200, backendTrades));
      });
      vi.stubGlobal('fetch', fetchMock);

      const result = await httpApiClient.analyzeProblem!("Le robinet fuit sous l'évier.");

      expect(result.trade).toBe('Plomberie');
      expect(result.priceEstimate).toBe('8 000 – 15 000 FCFA');
      expect(result.urgency).toBe('normale');
      expect(result.suggestedDevis).toEqual({
        title: 'Plomberie',
        labor: 8000,
        materials: 4000,
        total: 12000,
      });

      const [analyzeUrl, analyzeOptions] = fetchMock.mock.calls.find((call: unknown[]) =>
        (call[0] as string).includes('/ai/analyze'),
      ) as [string, RequestInit];
      expect(analyzeUrl).toContain('/api/v1/ai/analyze');
      expect(analyzeOptions.method).toBe('POST');
      expect(JSON.parse(analyzeOptions.body as string)).toEqual({
        description: "Le robinet fuit sous l'évier.",
      });
    });

    it('maps urgent/immediat to their French display labels', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation((url: string) => {
          if (url.includes('/ai/analyze')) {
            return Promise.resolve(jsonResponse(200, { ...backendTriageResult, urgency: 'immediat' }));
          }
          return Promise.resolve(jsonResponse(200, backendTrades));
        }),
      );

      const result = await httpApiClient.analyzeProblem!('Fuite urgente.');
      expect(result.urgency).toBe('immédiate');
    });

    it('falls back to the raw trade_code when it is missing from the trades list', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation((url: string) => {
          if (url.includes('/ai/analyze')) {
            return Promise.resolve(jsonResponse(200, { ...backendTriageResult, trade_code: 'peinture' }));
          }
          return Promise.resolve(jsonResponse(200, backendTrades));
        }),
      );

      const result = await httpApiClient.analyzeProblem!('...');
      expect(result.trade).toBe('peinture');
    });

    it('propagates a backend error (e.g. rate limited) as an ApiError', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation((url: string) => {
          if (url.includes('/ai/analyze')) {
            return Promise.resolve(
              jsonResponse(429, {
                error: { code: 'TROP_DE_DEMANDES', message: "Trop de demandes d'analyse IA, merci de réessayer plus tard." },
              }),
            );
          }
          return Promise.resolve(jsonResponse(200, backendTrades));
        }),
      );

      const promise = httpApiClient.analyzeProblem!('...');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({
        code: 'validation',
        message: "Trop de demandes d'analyse IA, merci de réessayer plus tard.",
      });
    });
  });
});
