import { describe, expect, it, vi } from 'vitest';
import { mockApiClient } from './mock';
import { ApiError } from './types';

describe('mockApiClient', () => {
  describe('listArtisans', () => {
    it('resolves with all seeded artisans', async () => {
      const artisans = await mockApiClient.listArtisans();
      expect(artisans.length).toBeGreaterThan(0);
      expect(artisans.some((a) => a.id === 'idrissa-diop')).toBe(true);
    });

    it('filters by trade', async () => {
      const artisans = await mockApiClient.listArtisans({ trade: 'Électricité' });
      expect(artisans.length).toBeGreaterThan(0);
      expect(artisans.every((a) => a.trade === 'Électricité')).toBe(true);
    });

    it('filters by search across name/trade/tags', async () => {
      const artisans = await mockApiClient.listArtisans({ search: 'climatisation' });
      expect(artisans.length).toBeGreaterThan(0);
      expect(
        artisans.every(
          (a) =>
            a.name.toLowerCase().includes('climatisation') ||
            a.trade.toLowerCase().includes('climatisation') ||
            a.tags.some((tag) => tag.toLowerCase().includes('climatisation')),
        ),
      ).toBe(true);
    });

    it('filters by minimum rating', async () => {
      const all = await mockApiClient.listArtisans();
      const filtered = await mockApiClient.listArtisans({ minRating: 4.9 });
      expect(filtered.every((a) => a.rating >= 4.9)).toBe(true);
      expect(filtered.length).toBeLessThan(all.length);
    });
  });

  describe('getArtisanById', () => {
    it('resolves the matching artisan', async () => {
      const artisan = await mockApiClient.getArtisanById('idrissa-diop');
      expect(artisan.name).toBe('Idrissa Diop');
    });

    it('rejects with a not_found ApiError for an unknown id', async () => {
      const promise = mockApiClient.getArtisanById('does-not-exist');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: 'not_found' });
    });
  });

  describe('getArtisanStats', () => {
    it('resolves stats for a known artisan', async () => {
      const stats = await mockApiClient.getArtisanStats('idrissa-diop');
      expect(stats.interventionsCount).toBeGreaterThan(0);
      expect(stats.revenueFcfa).toBeGreaterThan(0);
    });

    it('rejects with a not_found ApiError for an artisan without stats', async () => {
      const promise = mockApiClient.getArtisanStats('does-not-exist');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: 'not_found' });
    });
  });

  describe('analyzeProblem', () => {
    it('resolves a fixed, offline analysis -- never a network call', async () => {
      const fetchSpy = vi.fn();
      vi.stubGlobal('fetch', fetchSpy);
      try {
        const result = await mockApiClient.analyzeProblem("Une fuite sous l'évier");
        expect(result.tradeCode).toBe('plomberie');
        expect(result.suggestedDevis.total).toBe(
          result.suggestedDevis.labor + result.suggestedDevis.materials,
        );
        expect(fetchSpy).not.toHaveBeenCalled();
      } finally {
        vi.unstubAllGlobals();
      }
    });

    it('rejects an empty description with a validation ApiError', async () => {
      const promise = mockApiClient.analyzeProblem('   ');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: 'validation' });
    });
  });
});
