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
      // Prix indicatif réel, issu du tarif horaire déclaré (jamais inventé).
      expect(artisan.priceBase).toBe('Dès 15 000 FCFA/h');
      expect(artisan.priceNumber).toBe(15000);
      // Codes métier conservés à côté des libellés (nécessaires à la demande de devis).
      expect(artisan.tags).toEqual(['Plomberie']);
      expect(artisan.tradeCodes).toEqual(['plomberie']);
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

    it('affiche le tarif horaire le plus bas quand l’artisan déclare plusieurs métiers', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [
              {
                ...backendArtisan,
                trades: [
                  { ...backendArtisan.trades[0], hourly_rate_fcfa: 20000 },
                  {
                    ...backendArtisan.trades[0],
                    trade: { id: 't2', code: 'electricite', label_fr: 'Électricité' },
                    hourly_rate_fcfa: 8000,
                  },
                ],
              },
            ],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const [artisan] = await httpApiClient.listArtisans!();
      expect(artisan.priceBase).toBe('Dès 8 000 FCFA/h');
      expect(artisan.priceNumber).toBe(8000);
    });

    it('n’invente aucun prix quand aucun métier n’est déclaré', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [{ ...backendArtisan, trades: [] }],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const [artisan] = await httpApiClient.listArtisans!();
      expect(artisan.priceBase).toBe('Tarif sur devis');
      expect(artisan.priceNumber).toBe(0);
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
        .mockResolvedValue(
          jsonResponse(200, {
            items: [],
            pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
          }),
        );
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
        return Promise.resolve(
          jsonResponse(200, { ...backendArtisan, cover_url: '/images/cover.jpg' }),
        );
      });
      vi.stubGlobal('fetch', fetchMock);

      const artisan = await httpApiClient.getArtisanById!('a1');

      expect(artisan.coverUrl).toBe('/images/cover.jpg');
      expect(artisan.reviews).toHaveLength(1);
      expect(artisan.reviews[0]).toMatchObject({
        author: 'Fatou Kane',
        rating: 5,
        avatarInitials: 'FK',
      });
    });

    it('propagates the backend 404 message as-is (already French, display-ready)', async () => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValue(
            jsonResponse(404, {
              error: { code: 'ARTISAN_NOT_FOUND', message: 'Artisan introuvable.' },
            }),
          ),
      );

      const promise = httpApiClient.getArtisanById!('does-not-exist');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({
        code: 'not_found',
        message: 'Artisan introuvable.',
      });
    });
  });

  describe('getArtisanStats', () => {
    it('maps the public stats shape (no revenue_fcfa in the response body)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            rating_avg: 4.8,
            review_count: 12,
            interventions_count: 9,
            response_rate: null,
          }),
        ),
      );

      const stats = await httpApiClient.getArtisanStats!('a1');

      expect(stats).toEqual({
        ratingAvg: 4.8,
        reviewCount: 12,
        interventionsCount: 9,
        responseRate: null,
        revenueFcfa: null,
      });
    });

    it('maps the private stats shape (owner/admin, revenue_fcfa present) without inventing it otherwise', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            rating_avg: 4.8,
            review_count: 12,
            interventions_count: 9,
            response_rate: null,
            revenue_fcfa: 150000,
          }),
        ),
      );

      const stats = await httpApiClient.getArtisanStats!('a1');
      expect(stats.revenueFcfa).toBe(150000);
    });
  });

  describe('updateArtisanAvailability', () => {
    it('sends a PATCH to /artisans/me with is_available and maps the updated Artisan', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendArtisan, is_available: false }));
      vi.stubGlobal('fetch', fetchMock);

      const artisan = await httpApiClient.updateArtisanAvailability!(false);

      expect(artisan.available).toBe(false);
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/artisans/me');
      expect(options.method).toBe('PATCH');
      expect(JSON.parse(options.body as string)).toEqual({ is_available: false });
    });

    it('propagates a backend error (e.g. role check) as an ApiError', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(403, {
            error: {
              code: 'ROLE_INSUFFISANT',
              message: "Vous n'avez pas les droits nécessaires pour cette action.",
            },
          }),
        ),
      );

      const promise = httpApiClient.updateArtisanAvailability!(true);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({
        message: "Vous n'avez pas les droits nécessaires pour cette action.",
      });
    });
  });

  describe('getMyArtisanProfile', () => {
    it('maps every declared trade with its own id (unlike mapArtisan, which flattens to a single trade label)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            ...backendArtisan,
            cover_url: null,
            trades: [
              {
                id: 'at-1',
                trade: { id: 't1', code: 'plomberie', label_fr: 'Plomberie' },
                hourly_rate_fcfa: 15000,
                service_radius_m: 5000,
                has_custom_service_area: false,
              },
              {
                id: 'at-2',
                trade: { id: 't2', code: 'electricite', label_fr: 'Électricité' },
                hourly_rate_fcfa: 20000,
                service_radius_m: 8000,
                has_custom_service_area: true,
              },
            ],
          }),
        ),
      );

      const profile = await httpApiClient.getMyArtisanProfile!('a1');

      expect(profile.fullName).toBe('Idrissa Diop');
      expect(profile.verifiedStatus).toBe('verified');
      expect(profile.trades).toEqual([
        {
          id: 'at-1',
          tradeCode: 'plomberie',
          tradeLabel: 'Plomberie',
          hourlyRateFcfa: 15000,
          serviceRadiusM: 5000,
          hasCustomServiceArea: false,
        },
        {
          id: 'at-2',
          tradeCode: 'electricite',
          tradeLabel: 'Électricité',
          hourlyRateFcfa: 20000,
          serviceRadiusM: 8000,
          hasCustomServiceArea: true,
        },
      ]);
    });
  });

  describe('updateMyArtisanProfile', () => {
    it('only sends the fields actually provided (partial update)', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendArtisan, cover_url: null }));
      vi.stubGlobal('fetch', fetchMock);

      await httpApiClient.updateMyArtisanProfile!({ bio: 'Nouvelle bio.' });

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/artisans/me');
      expect(options.method).toBe('PATCH');
      expect(JSON.parse(options.body as string)).toEqual({ bio: 'Nouvelle bio.' });
    });

    it('forwards baseLocation and null-clearing fields verbatim', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendArtisan, cover_url: null }));
      vi.stubGlobal('fetch', fetchMock);

      await httpApiClient.updateMyArtisanProfile!({
        bio: null,
        yearsExperience: 5,
        baseLocation: { lat: 14.7, lng: -17.4 },
      });

      const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(JSON.parse(options.body as string)).toEqual({
        bio: null,
        years_experience: 5,
        base_location: { lat: 14.7, lng: -17.4 },
      });
    });

    it('sends cover_url and maps it back onto the returned profile', async () => {
      const coverUrl = 'https://cdn.example.invalid/covers/atelier.jpg';
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendArtisan, cover_url: coverUrl }));
      vi.stubGlobal('fetch', fetchMock);

      const profile = await httpApiClient.updateMyArtisanProfile!({ coverUrl });

      const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(JSON.parse(options.body as string)).toEqual({ cover_url: coverUrl });
      expect(profile.coverUrl).toBe(coverUrl);
    });
  });

  describe('uploadAvatar', () => {
    it('sends a multipart POST with the file, never JSON-serialized', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, {
          ...backendArtisan,
          cover_url: null,
          avatar_url: 'http://localhost:8000/static/avatars/a1/abc.jpg',
        }),
      );
      vi.stubGlobal('fetch', fetchMock);
      const file = new File(['fake-image-bytes'], 'avatar.jpg', { type: 'image/jpeg' });

      const profile = await httpApiClient.uploadAvatar!(file);

      expect(profile.avatarUrl).toBe('http://localhost:8000/static/avatars/a1/abc.jpg');
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/artisans/me/avatar');
      expect(options.method).toBe('POST');
      expect(options.body).toBeInstanceOf(FormData);
      const body = options.body as FormData;
      expect(body.get('file')).toBe(file);
    });

    it('propagates a magic-bytes rejection as an ApiError', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            error: {
              code: 'AVATAR_TYPE_INVALIDE',
              message: 'La photo de profil doit être une image JPEG ou PNG.',
            },
          }),
        ),
      );
      const file = new File(['not-an-image'], 'fake.jpg', { type: 'image/jpeg' });

      const promise = httpApiClient.uploadAvatar!(file);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({
        message: 'La photo de profil doit être une image JPEG ou PNG.',
      });
    });
  });

  describe('uploadCover', () => {
    it('sends a multipart POST to /artisans/me/cover and maps the new cover URL', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, {
          ...backendArtisan,
          cover_url: 'http://localhost:8000/static/avatars/a1/cover-abc.jpg',
        }),
      );
      vi.stubGlobal('fetch', fetchMock);
      const file = new File(['fake-image-bytes'], 'cover.jpg', { type: 'image/jpeg' });

      const profile = await httpApiClient.uploadCover!(file);

      expect(profile.coverUrl).toBe('http://localhost:8000/static/avatars/a1/cover-abc.jpg');
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/artisans/me/cover');
      expect(options.method).toBe('POST');
      expect(options.body).toBeInstanceOf(FormData);
      expect((options.body as FormData).get('file')).toBe(file);
    });

    it('propagates the shared rate-limit rejection (429) with its French message', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(429, {
            error: {
              code: 'TROP_DE_DEMANDES',
              message: "Trop d'envois de photo, merci de réessayer plus tard.",
            },
          }),
        ),
      );
      const file = new File(['fake-image-bytes'], 'cover.png', { type: 'image/png' });

      const promise = httpApiClient.uploadCover!(file);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({
        message: "Trop d'envois de photo, merci de réessayer plus tard.",
      });
    });
  });

  describe('getProfileMediaConstraints', () => {
    it('maps the server constraints (single source of truth)', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, {
          accepted_mime_types: ['image/jpeg', 'image/png'],
          max_pixels: 50_000_000,
          avatar: { max_upload_bytes: 10_485_760, max_side_px: 512 },
          cover: { max_upload_bytes: 10_485_760, max_side_px: 1600 },
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const constraints = await httpApiClient.getProfileMediaConstraints!();

      expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/artisans/me/media-constraints');
      expect(constraints).toEqual({
        acceptedMimeTypes: ['image/jpeg', 'image/png'],
        maxPixels: 50_000_000,
        avatar: { maxUploadBytes: 10_485_760, maxSidePx: 512 },
        cover: { maxUploadBytes: 10_485_760, maxSidePx: 1600 },
      });
    });
  });

  describe('addArtisanTrade', () => {
    it('sends a POST to /artisans/me/trades and maps the updated profile', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(201, { ...backendArtisan, cover_url: null }));
      vi.stubGlobal('fetch', fetchMock);

      await httpApiClient.addArtisanTrade!({
        tradeCode: 'plomberie',
        hourlyRateFcfa: 12000,
        serviceRadiusM: 8000,
      });

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/artisans/me/trades');
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body as string)).toEqual({
        trade_code: 'plomberie',
        hourly_rate_fcfa: 12000,
        service_radius_m: 8000,
      });
    });

    it('propagates a backend rejection (e.g. already declared) as an ApiError', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(409, {
            error: { code: 'ARTISAN_METIER_DEJA_DECLARE', message: 'Vous exercez déjà ce métier.' },
          }),
        ),
      );

      const promise = httpApiClient.addArtisanTrade!({
        tradeCode: 'plomberie',
        hourlyRateFcfa: 12000,
        serviceRadiusM: 8000,
      });
      await expect(promise).rejects.toMatchObject({ message: 'Vous exercez déjà ce métier.' });
    });
  });

  describe('removeArtisanTrade', () => {
    it('sends a DELETE to /artisans/me/trades/{id}', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendArtisan, trades: [], cover_url: null }));
      vi.stubGlobal('fetch', fetchMock);

      const profile = await httpApiClient.removeArtisanTrade!('at-1');

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/artisans/me/trades/at-1');
      expect(options.method).toBe('DELETE');
      expect(profile.trades).toEqual([]);
    });
  });

  describe('listMyVerificationDocuments', () => {
    it('maps the verified status and document metadata (never a binary)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            verified_status: 'pending',
            documents: [
              {
                id: 'doc-1',
                doc_type: 'cni',
                status: 'pending',
                note: null,
                created_at: '2026-01-01T00:00:00Z',
                reviewed_at: null,
              },
              {
                id: 'doc-2',
                doc_type: 'selfie',
                status: 'rejected',
                note: 'Photo floue.',
                created_at: '2026-01-02T00:00:00Z',
                reviewed_at: '2026-01-03T00:00:00Z',
              },
            ],
          }),
        ),
      );

      const verification = await httpApiClient.listMyVerificationDocuments!();

      expect(verification.verifiedStatus).toBe('pending');
      expect(verification.documents).toEqual([
        {
          id: 'doc-1',
          docType: 'cni',
          status: 'pending',
          note: null,
          createdAt: '2026-01-01T00:00:00Z',
          reviewedAt: null,
        },
        {
          id: 'doc-2',
          docType: 'selfie',
          status: 'rejected',
          note: 'Photo floue.',
          createdAt: '2026-01-02T00:00:00Z',
          reviewedAt: '2026-01-03T00:00:00Z',
        },
      ]);
    });
  });

  describe('uploadVerificationDocument', () => {
    it('sends a multipart POST with doc_type and file, never JSON-serialized', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(201, {
          id: 'doc-1',
          doc_type: 'cni',
          status: 'pending',
          note: null,
          created_at: '2026-01-01T00:00:00Z',
          reviewed_at: null,
        }),
      );
      vi.stubGlobal('fetch', fetchMock);
      const file = new File(['fake-image-bytes'], 'cni.jpg', { type: 'image/jpeg' });

      const document = await httpApiClient.uploadVerificationDocument!('cni', file);

      expect(document).toEqual({
        id: 'doc-1',
        docType: 'cni',
        status: 'pending',
        note: null,
        createdAt: '2026-01-01T00:00:00Z',
        reviewedAt: null,
      });
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/artisans/me/documents');
      expect(options.method).toBe('POST');
      expect(options.body).toBeInstanceOf(FormData);
      // Pas de header Content-Type fixé explicitement : c'est le navigateur
      // qui doit poser sa propre frontière multipart, qu'apiRequest
      // écraserait s'il forçait application/json ici (voir http.ts buildHeaders).
      const headers = options.headers as Record<string, string> | undefined;
      expect(headers?.['Content-Type']).toBeUndefined();
      const body = options.body as FormData;
      expect(body.get('doc_type')).toBe('cni');
      expect(body.get('file')).toBe(file);
    });

    it('propagates a magic-bytes rejection as an ApiError', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            error: {
              code: 'FICHIER_TYPE_INVALIDE',
              message: "Le fichier fourni n'est pas d'un type accepté pour ce document.",
            },
          }),
        ),
      );
      const file = new File(['not-an-image'], 'fake.jpg', { type: 'image/jpeg' });

      const promise = httpApiClient.uploadVerificationDocument!('cni', file);
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({
        message: "Le fichier fourni n'est pas d'un type accepté pour ce document.",
      });
    });
  });

  describe('listTrades', () => {
    it('maps the backend trade reference list', async () => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValue(
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
        if (url.includes('/ai/analyze'))
          return Promise.resolve(jsonResponse(200, backendTriageResult));
        return Promise.resolve(jsonResponse(200, backendTrades));
      });
      vi.stubGlobal('fetch', fetchMock);

      const result = await httpApiClient.analyzeProblem!("Le robinet fuit sous l'évier.");

      expect(result.trade).toBe('Plomberie');
      expect(result.tradeCode).toBe('plomberie');
      expect(result.priceEstimate).toBe('8 000 – 15 000 FCFA');
      expect(result.priceMinFcfa).toBe(8000);
      expect(result.priceMaxFcfa).toBe(15000);
      expect(result.urgency).toBe('normale');
      expect(result.urgencyCode).toBe('normal');
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
            return Promise.resolve(
              jsonResponse(200, { ...backendTriageResult, urgency: 'immediat' }),
            );
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
            return Promise.resolve(
              jsonResponse(200, { ...backendTriageResult, trade_code: 'peinture' }),
            );
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
                error: {
                  code: 'TROP_DE_DEMANDES',
                  message: "Trop de demandes d'analyse IA, merci de réessayer plus tard.",
                },
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

  describe('createServiceRequest', () => {
    const backendServiceRequest = {
      id: 'req-1',
      client_id: 'u1',
      trade: { id: 't2', code: 'electricite', label_fr: 'Électricité' },
      description: 'Une prise ne fonctionne plus.',
      photo_url: null,
      location: { lat: 14.7256, lng: -17.4914 },
      location_label: 'Ouakam, Dakar',
      urgency: 'urgent',
      ai_estimate_min_fcfa: 12000,
      ai_estimate_max_fcfa: 25000,
      status: 'ouverte',
      created_at: '2026-01-01T00:00:00Z',
    };

    it('posts the snake_case payload and maps the created request back', async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, backendServiceRequest));
      vi.stubGlobal('fetch', fetchMock);

      const result = await httpApiClient.createServiceRequest!({
        tradeCode: 'electricite',
        description: 'Une prise ne fonctionne plus.',
        photoUrl: null,
        location: { lat: 14.7256, lng: -17.4914 },
        locationLabel: 'Ouakam, Dakar',
        urgency: 'urgent',
        aiEstimateMinFcfa: 12000,
        aiEstimateMaxFcfa: 25000,
      });

      expect(result).toEqual({
        id: 'req-1',
        tradeCode: 'electricite',
        tradeLabel: 'Électricité',
        description: 'Une prise ne fonctionne plus.',
        photoUrl: null,
        location: { lat: 14.7256, lng: -17.4914 },
        locationLabel: 'Ouakam, Dakar',
        urgency: 'urgent',
        aiEstimateMinFcfa: 12000,
        aiEstimateMaxFcfa: 25000,
        status: 'ouverte',
        createdAt: '2026-01-01T00:00:00Z',
      });

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/requests');
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body as string)).toEqual({
        trade_code: 'electricite',
        description: 'Une prise ne fonctionne plus.',
        photo_url: null,
        location: { lat: 14.7256, lng: -17.4914 },
        location_label: 'Ouakam, Dakar',
        urgency: 'urgent',
        ai_estimate_min_fcfa: 12000,
        ai_estimate_max_fcfa: 25000,
      });
    });

    it('propagates a backend validation error (e.g. unknown trade) as an ApiError', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            error: {
              code: 'METIER_INCONNU',
              message: 'Le métier demandé est introuvable ou inactif.',
            },
          }),
        ),
      );

      const promise = httpApiClient.createServiceRequest!({
        tradeCode: 'inexistant',
        description: 'Test.',
        location: { lat: 0, lng: 0 },
        locationLabel: 'Dakar Plateau',
        urgency: 'normal',
      });

      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({
        message: 'Le métier demandé est introuvable ou inactif.',
      });
    });
  });

  describe('éligibilité et couverture (lieu)', () => {
    it("lit, pour chaque demande ouverte, si l'artisan peut la recevoir", async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, [
          { request_id: 'r1', eligible: true, reason: null },
          { request_id: 'r2', eligible: false, reason: 'hors_zone' },
        ]),
      );
      vi.stubGlobal('fetch', fetchMock);

      const result = await httpApiClient.listRequestEligibility!('a1');

      expect(result).toEqual([
        { requestId: 'r1', eligible: true, reason: null },
        { requestId: 'r2', eligible: false, reason: 'hors_zone' },
      ]);
      expect(fetchMock.mock.calls[0][0]).toMatch(/\/requests\/me\/eligibility\?artisan_id=a1$/);
    });

    it('interroge la couverture d’un lieu pour un métier', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { eligible: false, reason: 'hors_zone' }));
      vi.stubGlobal('fetch', fetchMock);

      const result = await httpApiClient.checkArtisanCoverage!('a1', 'plomberie', {
        lat: 14.6681,
        lng: -17.4339,
      });

      expect(result).toEqual({ eligible: false, reason: 'hors_zone' });
      expect(fetchMock.mock.calls[0][0]).toMatch(
        /\/artisans\/a1\/coverage\?trade=plomberie&lat=14\.6681&lng=-17\.4339$/,
      );
    });
  });

  describe('listMyServiceRequests', () => {
    it('unwraps the paginated envelope into a flat ServiceRequest[]', async () => {
      const backendServiceRequest = {
        id: 'req-1',
        client_id: 'u1',
        trade: { id: 't1', code: 'plomberie', label_fr: 'Plomberie' },
        description: 'Fuite sous l’évier.',
        photo_url: null,
        location: { lat: 14.6937, lng: -17.4441 },
        urgency: 'normal',
        ai_estimate_min_fcfa: null,
        ai_estimate_max_fcfa: null,
        status: 'ouverte',
        created_at: '2026-01-01T00:00:00Z',
      };
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [backendServiceRequest],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const requests = await httpApiClient.listMyServiceRequests!();

      expect(requests).toHaveLength(1);
      expect(requests[0]).toMatchObject({
        id: 'req-1',
        tradeLabel: 'Plomberie',
        status: 'ouverte',
      });
    });
  });

  describe('interventions and quotes (Lot 12b)', () => {
    const backendServiceRequest = {
      id: 'req-1',
      client_id: 'u1',
      trade: { id: 't1', code: 'plomberie', label_fr: 'Plomberie' },
      description: 'Fuite sous l’évier.',
      photo_url: null,
      location: { lat: 14.6937, lng: -17.4441 },
      urgency: 'normal',
      ai_estimate_min_fcfa: null,
      ai_estimate_max_fcfa: null,
      status: 'en_relation',
      created_at: '2026-01-01T00:00:00Z',
    };

    const backendIntervention = {
      id: 'int-1',
      service_request: backendServiceRequest,
      client_id: 'u1',
      artisan_id: 'a1',
      status: 'acceptee',
      commission_rate_bps: 1000,
      agreed_amount_fcfa: null,
      scheduled_at: null,
      completed_at: null,
      cancellation: null,
      quote: {
        id: 'q1',
        labor_fcfa: 15000,
        materials_fcfa: 5000,
        total_fcfa: 20000,
        status: 'propose',
        created_at: '2026-01-02T00:00:00Z',
      },
      review: null,
      created_at: '2026-01-01T00:00:00Z',
    };

    it('listMyInterventions unwraps the paginated envelope and maps nested service_request/quote', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [backendIntervention],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const interventions = await httpApiClient.listMyInterventions!();

      expect(interventions).toHaveLength(1);
      expect(interventions[0]).toMatchObject({
        id: 'int-1',
        status: 'acceptee',
        commissionRateBps: 1000,
        serviceRequest: { id: 'req-1', tradeLabel: 'Plomberie' },
        quote: { id: 'q1', totalFcfa: 20000, status: 'propose' },
        review: null,
      });
    });

    it('getInterventionById maps a single intervention', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, backendIntervention)));

      const intervention = await httpApiClient.getInterventionById!('int-1');

      expect(intervention.id).toBe('int-1');
      expect(intervention.quote?.totalFcfa).toBe(20000);
    });

    it('createIntervention propose la demande à l’artisan (POST /interventions, snake_case)', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(
          jsonResponse(201, { ...backendIntervention, status: 'proposee', quote: null }),
        );
      vi.stubGlobal('fetch', fetchMock);

      const intervention = await httpApiClient.createIntervention!({
        serviceRequestId: 'req-1',
        artisanId: 'a1',
      });

      expect(intervention).toMatchObject({ id: 'int-1', status: 'proposee', quote: null });
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toMatch(/\/interventions$/);
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body as string)).toEqual({
        service_request_id: 'req-1',
        artisan_id: 'a1',
      });
    });

    it('createIntervention relaie tel quel le refus du serveur (ex. artisan hors zone)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            error: {
              code: 'ARTISAN_HORS_ZONE',
              message: "Cet artisan n'intervient pas dans votre zone.",
            },
          }),
        ),
      );

      await expect(
        httpApiClient.createIntervention!({ serviceRequestId: 'req-1', artisanId: 'a1' }),
      ).rejects.toThrow("Cet artisan n'intervient pas dans votre zone.");
    });

    it('acceptIntervention posts to /accept and maps the response', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendIntervention, status: 'acceptee' }));
      vi.stubGlobal('fetch', fetchMock);

      const intervention = await httpApiClient.acceptIntervention!('int-1');

      expect(intervention.status).toBe('acceptee');
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/interventions/int-1/accept');
      expect(options.method).toBe('POST');
    });

    it('declineIntervention posts the optional reason', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(
          jsonResponse(200, {
            ...backendIntervention,
            status: 'annulee',
            cancellation: {
              kind: 'refus',
              by: 'artisan',
              reason: 'Trop loin.',
              at: '2026-01-02T00:00:00Z',
            },
          }),
        );
      vi.stubGlobal('fetch', fetchMock);

      const intervention = await httpApiClient.declineIntervention!('int-1', 'Trop loin.');

      expect(intervention.cancellation).toEqual({
        kind: 'refus',
        by: 'artisan',
        reason: 'Trop loin.',
        at: '2026-01-02T00:00:00Z',
      });
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/interventions/int-1/decline');
      expect(JSON.parse(options.body as string)).toEqual({ reason: 'Trop loin.' });
    });

    it('createQuote posts labor/materials in snake_case, never a client-computed total', async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, backendIntervention));
      vi.stubGlobal('fetch', fetchMock);

      await httpApiClient.createQuote!('int-1', { laborFcfa: 15000, materialsFcfa: 5000 });

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/interventions/int-1/quote');
      const body = JSON.parse(options.body as string);
      expect(body).toEqual({ labor_fcfa: 15000, materials_fcfa: 5000 });
      expect(body.total_fcfa).toBeUndefined();
    });

    it('acceptQuote posts to /quote/accept', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendIntervention, status: 'en_cours' }));
      vi.stubGlobal('fetch', fetchMock);

      const intervention = await httpApiClient.acceptQuote!('int-1');

      expect(intervention.status).toBe('en_cours');
      const [url] = fetchMock.mock.calls[0] as [string];
      expect(url).toContain('/interventions/int-1/quote/accept');
    });

    it('refuseQuote posts to /quote/refuse', async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, backendIntervention));
      vi.stubGlobal('fetch', fetchMock);

      await httpApiClient.refuseQuote!('int-1');

      const [url] = fetchMock.mock.calls[0] as [string];
      expect(url).toContain('/interventions/int-1/quote/refuse');
    });

    it('completeIntervention posts to /complete', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ...backendIntervention, status: 'terminee' }));
      vi.stubGlobal('fetch', fetchMock);

      const intervention = await httpApiClient.completeIntervention!('int-1');

      expect(intervention.status).toBe('terminee');
      const [url] = fetchMock.mock.calls[0] as [string];
      expect(url).toContain('/interventions/int-1/complete');
    });

    it('createReview posts rating/comment and maps the returned Review', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(201, {
          id: 'rev-1',
          rating: 5,
          comment: 'Excellent travail.',
          author_name: 'Fatou Kane',
          created_at: '2026-01-03T00:00:00Z',
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const review = await httpApiClient.createReview!('int-1', {
        rating: 5,
        comment: 'Excellent travail.',
      });

      expect(review).toMatchObject({ id: 'rev-1', rating: 5, author: 'Fatou Kane' });
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/interventions/int-1/review');
      expect(JSON.parse(options.body as string)).toEqual({
        rating: 5,
        comment: 'Excellent travail.',
      });
    });
  });

  describe('messagerie', () => {
    const backendMessage = {
      id: 'm1',
      conversation_id: 'c1',
      seq: 42,
      sender_id: 'u1',
      body: 'Mon numéro : [numéro masqué]',
      contact_masked: true,
      has_attachment: false,
      attachment_content_type: null,
      created_at: '2026-10-11T10:00:00Z',
    };

    it('mappe un message (texte masqué, curseur seq)', async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, backendMessage));
      vi.stubGlobal('fetch', fetchMock);

      const message = await httpApiClient.sendMessage!('c1', 'Mon numéro : 77 123 45 67');

      expect(message).toEqual({
        id: 'm1',
        conversationId: 'c1',
        seq: 42,
        senderId: 'u1',
        body: 'Mon numéro : [numéro masqué]',
        contactMasked: true,
        hasAttachment: false,
        attachmentContentType: null,
        createdAt: '2026-10-11T10:00:00Z',
      });
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toMatch(/\/conversations\/c1\/messages$/);
      expect(JSON.parse(options.body as string)).toEqual({ body: 'Mon numéro : 77 123 45 67' });
    });

    it('relit les nouveaux messages avec le curseur since (repli polling)', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { items: [backendMessage], has_more: false }));
      vi.stubGlobal('fetch', fetchMock);

      const history = await httpApiClient.listMessages!('c1', { since: 41 });

      expect(history.items.map((m) => m.seq)).toEqual([42]);
      expect(history.hasMore).toBe(false);
      expect(fetchMock.mock.calls[0][0]).toMatch(/\/conversations\/c1\/messages\?since=41$/);
    });

    it('envoie une image en multipart, jamais en JSON', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(
          jsonResponse(201, { ...backendMessage, has_attachment: true, body: '' }),
        );
      vi.stubGlobal('fetch', fetchMock);
      const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'photo.jpg', {
        type: 'image/jpeg',
      });

      const message = await httpApiClient.sendImageMessage!('c1', file, 'La fuite');

      expect(message.hasAttachment).toBe(true);
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toMatch(/\/conversations\/c1\/messages\/image$/);
      expect(options.body).toBeInstanceOf(FormData);
      expect((options.body as FormData).get('caption')).toBe('La fuite');
      expect((options.headers as Record<string, string>)['Content-Type']).toBeUndefined();
    });

    it('mappe la liste des conversations et filtre par artisan', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, {
          items: [
            {
              id: 'c1',
              intervention_id: 'i1',
              intervention_status: 'acceptee',
              trade_label: 'Plomberie',
              other_party: {
                user_id: 'u2',
                role: 'artisan',
                display_name: 'Idrissa Fall',
                avatar_url: null,
                artisan_profile_id: 'a1',
              },
              last_message: {
                body: 'Je passe demain',
                from_me: false,
                has_attachment: false,
                created_at: '2026-10-11T10:00:00Z',
              },
              unread_count: 2,
              last_activity_at: '2026-10-11T10:00:00Z',
            },
          ],
          pagination: { page: 1, page_size: 50, total: 1, total_pages: 1 },
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const [conversation] = await httpApiClient.listConversations!({ artisanId: 'a1' });

      expect(conversation.otherParty.displayName).toBe('Idrissa Fall');
      expect(conversation.unreadCount).toBe(2);
      expect(conversation.lastMessage?.fromMe).toBe(false);
      expect(fetchMock.mock.calls[0][0]).toContain('artisan_id=a1');
    });

    it('obtient un ticket temps réel par un appel authentifié', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { ticket: 'jeton', expires_in: 60 }));
      vi.stubGlobal('fetch', fetchMock);

      const ticket = await httpApiClient.createRealtimeTicket!();

      expect(ticket).toEqual({ ticket: 'jeton', expiresIn: 60 });
      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toMatch(/\/realtime\/ticket$/);
      expect(options.method).toBe('POST');
    });
  });

  describe('paiements', () => {
    const backendIntervention = {
      id: 'int-1',
      service_request: {
        id: 'req-1',
        client_id: 'u1',
        trade: { id: 't1', code: 'plomberie', label_fr: 'Plomberie' },
        description: 'Fuite sous l’évier.',
        photo_url: null,
        location: { lat: 14.6937, lng: -17.4441 },
        urgency: 'normal',
        ai_estimate_min_fcfa: null,
        ai_estimate_max_fcfa: null,
        status: 'en_relation',
        created_at: '2026-01-01T00:00:00Z',
      },
      client_id: 'u1',
      artisan_id: 'a1',
      status: 'en_cours',
      commission_rate_bps: 1000,
      agreed_amount_fcfa: 12000,
      scheduled_at: null,
      completed_at: null,
      cancellation: null,
      quote: null,
      review: null,
      created_at: '2026-01-01T00:00:00Z',
    };
    const backendPayment = {
      amount_fcfa: 12000,
      commission: { rate_bps: 1000, amount_fcfa: 1200, status: 'due' },
      net_fcfa: 10800,
      status: 'en_attente',
      channel: 'wave',
      checkout_url: 'http://backend/api/v1/sandbox/checkout/jeton',
      checkout_expires_at: '2026-10-11T10:30:00Z',
      paid_at: null,
      released_at: null,
      refunded_at: null,
      payout: null,
    };

    it("ouvre un paiement en n'envoyant QUE l'intervention et le moyen, jamais un montant", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, backendPayment));
      vi.stubGlobal('fetch', fetchMock);

      const payment = await httpApiClient.initPayment!('int-1', 'wave');

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toMatch(/\/payments\/init$/);
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body as string)).toEqual({
        intervention_id: 'int-1',
        channel: 'wave',
      });
      expect(payment).toEqual({
        amountFcfa: 12000,
        commission: { rateBps: 1000, amountFcfa: 1200, status: 'due' },
        netFcfa: 10800,
        status: 'en_attente',
        channel: 'wave',
        checkoutUrl: 'http://backend/api/v1/sandbox/checkout/jeton',
        checkoutExpiresAt: '2026-10-11T10:30:00Z',
        paidAt: null,
        releasedAt: null,
        refundedAt: null,
        payout: null,
      });
    });

    it('lit les moyens de paiement proposés par le serveur', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            online_channels: ['wave', 'carte'],
            cash_enabled: false,
            currency: 'XOF',
          }),
        ),
      );

      expect(await httpApiClient.getPaymentOptions!()).toEqual({
        onlineChannels: ['wave', 'carte'],
        cashEnabled: false,
        currency: 'XOF',
      });
    });

    it('liste les paiements du client', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            items: [
              {
                id: 'p1',
                intervention_id: 'int-1',
                trade_label: 'Plomberie',
                artisan_name: 'Idrissa Fall',
                amount_fcfa: 12000,
                channel: 'cash',
                status: 'reussi',
                created_at: '2026-10-11T09:00:00Z',
                paid_at: '2026-10-11T09:00:00Z',
                released_at: null,
                refunded_at: null,
              },
            ],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const [payment] = await httpApiClient.listMyPayments!();

      expect(payment).toMatchObject({
        id: 'p1',
        interventionId: 'int-1',
        artisanName: 'Idrissa Fall',
        amountFcfa: 12000,
        channel: 'cash',
        status: 'reussi',
      });
    });

    it("lit les gains de l'artisan, synthèse et détail", async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(200, {
            totals: {
              paid_out_fcfa: 10800,
              payout_pending_fcfa: 0,
              in_escrow_fcfa: 4500,
              commission_collected_fcfa: 1200,
              cash_received_fcfa: 20000,
              commission_due_fcfa: 2000,
            },
            items: [
              {
                intervention_id: 'int-1',
                trade_label: 'Plomberie',
                client_name: 'Awa Diop',
                intervention_status: 'terminee',
                payment: { ...backendPayment, status: 'libere' },
              },
            ],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          }),
        ),
      );

      const earnings = await httpApiClient.getMyEarnings!();

      expect(earnings.totals).toEqual({
        paidOutFcfa: 10800,
        payoutPendingFcfa: 0,
        inEscrowFcfa: 4500,
        commissionCollectedFcfa: 1200,
        cashReceivedFcfa: 20000,
        commissionDueFcfa: 2000,
      });
      expect(earnings.items[0]).toMatchObject({
        clientName: 'Awa Diop',
        payment: { netFcfa: 10800, status: 'libere' },
      });
    });

    it('enregistre le moyen de versement sans jamais envoyer de numéro', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, {
          channel: 'orange_money',
          chosen: true,
          allowed_channels: ['wave', 'orange_money'],
          destination_phone: '+221770000001',
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const settings = await httpApiClient.updatePayoutSettings!('orange_money');

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toMatch(/\/payments\/me\/payout-settings$/);
      expect(options.method).toBe('PUT');
      expect(JSON.parse(options.body as string)).toEqual({ channel: 'orange_money' });
      expect(settings.destinationPhone).toBe('+221770000001');
    });

    it('annule, ouvre un litige et lit le volet financier de l’intervention', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, {
          ...backendIntervention,
          status: 'litige',
          payment: { ...backendPayment, status: 'retenu' },
          dispute: {
            opened_by: 'client',
            reason: 'Travaux non terminés.',
            opened_at: '2026-10-11T10:00:00Z',
            outcome: null,
            resolved_at: null,
            resolution_note: null,
          },
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const disputed = await httpApiClient.openDispute!('int-1', 'Travaux non terminés.');
      await httpApiClient.cancelIntervention!('int-1', null);

      expect(disputed.payment?.status).toBe('retenu');
      expect(disputed.dispute).toMatchObject({ openedBy: 'client', outcome: null });
      expect(fetchMock.mock.calls[0][0]).toMatch(/\/interventions\/int-1\/dispute$/);
      expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toEqual({
        reason: 'Travaux non terminés.',
      });
      expect(fetchMock.mock.calls[1][0]).toMatch(/\/interventions\/int-1\/cancel$/);
    });

    it("tranche un litige côté admin", async () => {
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, backendIntervention));
      vi.stubGlobal('fetch', fetchMock);

      await httpApiClient.resolveDispute!('int-1', 'rembourse', 'Travaux non réalisés.');

      const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toMatch(/\/admin\/disputes\/int-1\/resolve$/);
      expect(JSON.parse(options.body as string)).toEqual({
        outcome: 'rembourse',
        note: 'Travaux non réalisés.',
      });
    });
  });
});
