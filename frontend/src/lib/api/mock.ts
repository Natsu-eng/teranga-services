import {
  INITIAL_ARTISANS,
  INITIAL_JOB_REQUESTS,
  INITIAL_CHAT_MESSAGES,
  ARTISAN_STATS_BY_ID,
  CURRENT_USER,
} from '../../data/mockData';
import type { AIAnalysisResult, ChatMessage, ServiceRequest, Trade } from '../../types';
import {
  ApiError,
  type ApiClient,
  type ArtisanFilters,
  type CreateServiceRequestInput,
  type JobRequestFilters,
} from './types';

// Matches the trade codes seeded server-side (backend/scripts/seed.py) —
// this mock reference list only backs mockApiClient.listTrades, unused in
// production once index.ts routes listTrades to the HTTP implementation.
const MOCK_TRADES: Trade[] = [
  { id: 'trade-plomberie', code: 'plomberie', labelFr: 'Plomberie' },
  { id: 'trade-electricite', code: 'electricite', labelFr: 'Électricité' },
  { id: 'trade-climatisation', code: 'climatisation', labelFr: 'Climatisation' },
  { id: 'trade-menuiserie', code: 'menuiserie', labelFr: 'Menuiserie' },
  { id: 'trade-maconnerie', code: 'maconnerie', labelFr: 'Maçonnerie' },
  { id: 'trade-peinture', code: 'peinture', labelFr: 'Peinture' },
];

// Simulated network latency, in milliseconds. Screens must learn to handle
// loading/error states from day one, since Phase 2 swaps this for real HTTP.
const MIN_LATENCY_MS = 150;
const MAX_LATENCY_MS = 400;

function simulateNetworkLatency(): Promise<void> {
  const delay = MIN_LATENCY_MS + Math.random() * (MAX_LATENCY_MS - MIN_LATENCY_MS);
  return new Promise((resolve) => setTimeout(resolve, delay));
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

const DEFAULT_CONVERSATION_ID = INITIAL_ARTISANS[0]?.id ?? '';

// In-memory per-conversation store, keyed by conversationId (an artisan id today).
const conversations = new Map<string, ChatMessage[]>([
  [DEFAULT_CONVERSATION_ID, [...INITIAL_CHAT_MESSAGES]],
]);

function createMessageId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
}

interface RawAnalysisResponse {
  trade?: string;
  priceEstimate?: string;
  recommendedCount?: number;
  explanation?: string;
  urgency?: string;
  suggestedDevis?: {
    title?: string;
    labor?: number;
    materials?: number;
    total?: number;
  };
}

// This mock impl of analyzeProblem delegates to the legacy Express endpoint
// (see comment below) — dead in production (index.ts always routes
// analyzeProblem to httpApiClient) and its response shape never carries a
// trade_code/urgency enum, so tradeCode/urgencyCode/priceMin/MaxFcfa fall
// back to fixed defaults consistent with this function's other fallbacks.
const FALLBACK_TRADE_CODE = 'plomberie';
const FALLBACK_URGENCY_CODE: AIAnalysisResult['urgencyCode'] = 'normal';
const FALLBACK_PRICE_MIN_FCFA = 8_000;
const FALLBACK_PRICE_MAX_FCFA = 15_000;

export const mockApiClient: ApiClient = {
  async listArtisans(filters?: ArtisanFilters) {
    await simulateNetworkLatency();
    let results = [...INITIAL_ARTISANS];

    if (filters?.trade) {
      const trade = normalize(filters.trade);
      results = results.filter((artisan) => normalize(artisan.trade) === trade);
    }
    if (filters?.search) {
      const search = normalize(filters.search);
      results = results.filter(
        (artisan) =>
          normalize(artisan.name).includes(search) ||
          normalize(artisan.trade).includes(search) ||
          artisan.tags.some((tag) => normalize(tag).includes(search)),
      );
    }
    if (typeof filters?.minRating === 'number') {
      const minRating = filters.minRating;
      results = results.filter((artisan) => artisan.rating >= minRating);
    }

    return results;
  },

  async getArtisanById(id: string) {
    await simulateNetworkLatency();
    const artisan = INITIAL_ARTISANS.find((item) => item.id === id);
    if (!artisan) {
      throw new ApiError('not_found', "Cet artisan n'existe pas ou n'est plus disponible.");
    }
    return artisan;
  },

  async listJobRequests(filters?: JobRequestFilters) {
    await simulateNetworkLatency();
    let results = [...INITIAL_JOB_REQUESTS];
    if (filters?.status) {
      const status = filters.status;
      results = results.filter((job) => job.status === status);
    }
    return results;
  },

  async getChatMessages(conversationId: string) {
    await simulateNetworkLatency();
    return [...(conversations.get(conversationId) ?? [])];
  },

  async sendChatMessage(conversationId: string, text: string) {
    await simulateNetworkLatency();
    const trimmed = text.trim();
    if (!trimmed) {
      throw new ApiError('validation', 'Le message ne peut pas être vide.');
    }

    const message: ChatMessage = {
      id: createMessageId('msg'),
      sender: 'client',
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const existing = conversations.get(conversationId) ?? [];
    conversations.set(conversationId, [...existing, message]);

    // Simulate the artisan reading and replying shortly after, as a real
    // backend (or websocket) would — callers can re-fetch to observe it.
    setTimeout(() => {
      const reply: ChatMessage = {
        id: createMessageId('msg-artisan'),
        sender: 'artisan',
        text: 'Parfait ! Je peux intervenir dès cet après-midi vers 14h à votre adresse. Merci pour votre confiance.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      const current = conversations.get(conversationId) ?? [];
      conversations.set(conversationId, [...current, reply]);
    }, 1800);

    return message;
  },

  // Delegates to the existing /api/analyze-problem endpoint rather than mockData:
  // it's already a real, working integration (Gemini + heuristic fallback), so
  // routing it through this single entry point avoids a functional regression.
  async analyzeProblem(description: string): Promise<AIAnalysisResult> {
    let response: Response;
    try {
      response = await fetch('/api/analyze-problem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });
    } catch {
      throw new ApiError('network', "Impossible de contacter le service d'analyse IA.");
    }

    if (!response.ok) {
      throw new ApiError('network', "L'analyse IA a échoué. Merci de réessayer.");
    }

    const data = (await response.json()) as RawAnalysisResponse;
    return {
      trade: data.trade ?? 'Plomberie — fuite',
      tradeCode: FALLBACK_TRADE_CODE,
      priceEstimate: data.priceEstimate ?? '8 000 – 15 000 FCFA',
      priceMinFcfa: FALLBACK_PRICE_MIN_FCFA,
      priceMaxFcfa: FALLBACK_PRICE_MAX_FCFA,
      recommendedCount: data.recommendedCount ?? 3,
      explanation:
        data.explanation ??
        "L'IA a analysé votre description pour identifier les meilleurs experts disponibles immédiatement à Dakar.",
      urgency: data.urgency ?? 'moyenne',
      urgencyCode: FALLBACK_URGENCY_CODE,
      suggestedDevis: {
        title: data.suggestedDevis?.title ?? "Réparation de fuite d'eau",
        labor: data.suggestedDevis?.labor ?? 8000,
        materials: data.suggestedDevis?.materials ?? 4000,
        total: data.suggestedDevis?.total ?? 12000,
      },
    };
  },

  async getArtisanStats(artisanId: string) {
    await simulateNetworkLatency();
    const stats = ARTISAN_STATS_BY_ID[artisanId];
    if (!stats) {
      throw new ApiError('not_found', 'Statistiques indisponibles pour cet artisan.');
    }
    return stats;
  },

  async getCurrentUser() {
    await simulateNetworkLatency();
    return CURRENT_USER;
  },

  async listTrades() {
    await simulateNetworkLatency();
    return [...MOCK_TRADES];
  },

  // Dead in production (index.ts always routes these to httpApiClient) — kept
  // only so mockApiClient remains a complete ApiClient for mock.test.ts.
  async createServiceRequest(input: CreateServiceRequestInput): Promise<ServiceRequest> {
    await simulateNetworkLatency();
    const trade = MOCK_TRADES.find((item) => item.code === input.tradeCode);
    return {
      id: createMessageId('request'),
      tradeCode: input.tradeCode,
      tradeLabel: trade?.labelFr ?? input.tradeCode,
      description: input.description,
      photoUrl: input.photoUrl ?? null,
      location: input.location,
      urgency: input.urgency,
      aiEstimateMinFcfa: input.aiEstimateMinFcfa ?? null,
      aiEstimateMaxFcfa: input.aiEstimateMaxFcfa ?? null,
      status: 'ouverte',
      createdAt: new Date().toISOString(),
    };
  },

  async listMyServiceRequests(): Promise<ServiceRequest[]> {
    await simulateNetworkLatency();
    return [];
  },
};
