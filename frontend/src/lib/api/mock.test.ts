import { afterEach, describe, expect, it, vi } from 'vitest';
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

  describe('listJobRequests', () => {
    it('resolves with all seeded job requests', async () => {
      const requests = await mockApiClient.listJobRequests();
      expect(requests.length).toBeGreaterThan(0);
    });

    it('filters by status', async () => {
      const newRequests = await mockApiClient.listJobRequests({ status: 'new' });
      expect(newRequests.length).toBeGreaterThan(0);
      expect(newRequests.every((r) => r.status === 'new')).toBe(true);

      const acceptedRequests = await mockApiClient.listJobRequests({ status: 'accepted' });
      expect(acceptedRequests).toEqual([]);
    });
  });

  describe('getChatMessages', () => {
    it('resolves with the seeded conversation for the default artisan', async () => {
      const messages = await mockApiClient.getChatMessages('idrissa-diop');
      expect(messages.length).toBeGreaterThan(0);
    });

    it('resolves with an empty conversation for an unknown conversationId', async () => {
      const messages = await mockApiClient.getChatMessages('brand-new-conversation');
      expect(messages).toEqual([]);
    });
  });

  describe('sendChatMessage', () => {
    it('appends the message and makes it retrievable', async () => {
      const conversationId = 'test-conversation-send';
      const sent = await mockApiClient.sendChatMessage(conversationId, 'Bonjour !');
      expect(sent.sender).toBe('client');
      expect(sent.text).toBe('Bonjour !');

      const messages = await mockApiClient.getChatMessages(conversationId);
      expect(messages).toHaveLength(1);
      expect(messages[0].id).toBe(sent.id);
    });

    it('rejects with a validation ApiError for an empty message', async () => {
      const promise = mockApiClient.sendChatMessage('test-conversation-empty', '   ');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: 'validation' });
    });
  });

  describe('getArtisanStats', () => {
    it('resolves stats for a known artisan', async () => {
      const stats = await mockApiClient.getArtisanStats('idrissa-diop');
      expect(stats.acceptedRequestsCount).toBeGreaterThan(0);
      expect(stats.weeklyRevenues.length).toBeGreaterThan(0);
    });

    it('rejects with a not_found ApiError for an artisan without stats', async () => {
      const promise = mockApiClient.getArtisanStats('does-not-exist');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: 'not_found' });
    });
  });

  describe('getCurrentUser', () => {
    it('resolves the current user, linked to an artisan profile', async () => {
      const user = await mockApiClient.getCurrentUser();
      expect(user.artisanId).toBe('idrissa-diop');
    });
  });

  describe('analyzeProblem', () => {
    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('resolves with the parsed analysis on a successful response', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({ trade: 'Électricité — panne', priceEstimate: '10 000 FCFA' }),
        }),
      );

      const result = await mockApiClient.analyzeProblem('Une prise ne fonctionne plus');
      expect(result.trade).toBe('Électricité — panne');
      expect(result.priceEstimate).toBe('10 000 FCFA');
      // Falls back to defaults for fields the (stubbed) response omitted.
      expect(result.suggestedDevis.total).toBe(12000);
    });

    it('rejects with a network ApiError when the response is not ok', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));

      const promise = mockApiClient.analyzeProblem('...');
      await expect(promise).rejects.toBeInstanceOf(ApiError);
      await expect(promise).rejects.toMatchObject({ code: 'network' });
    });
  });
});
