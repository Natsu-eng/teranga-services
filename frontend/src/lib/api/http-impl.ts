/**
 * HTTP implementation of `ApiClient`, backed by the FastAPI backend
 * (Lots 6-9). Only the methods the backend actually covers are implemented
 * here — `index.ts` is the single place that decides, per method, whether
 * to use this or `mockApiClient` (see its top-of-file comment).
 *
 * Schema adaptation: the backend's artisan schemas (`app/schemas/artisans.py`)
 * intentionally omit any contact field (phone/email — anti-disintermediation,
 * BUILD_PLAN.md Lot 9) and don't carry several fields the mock UI model
 * invented (a public hourly price, a human-readable "location", a weekly
 * revenue breakdown...). Rather than fabricate values, missing fields map to
 * neutral, honest placeholders (see `mapArtisan` below) — never an invented
 * number or address.
 */
import type {
  AIAnalysisResult,
  Artisan,
  ArtisanStats,
  Intervention,
  Quote,
  Review,
  ServiceRequest,
  Trade,
} from '../../types';
import { apiRequest } from './http';
import type {
  ApiClient,
  ArtisanFilters,
  CreateQuoteInput,
  CreateReviewInput,
  CreateServiceRequestInput,
} from './types';

interface BackendTrade {
  id: string;
  code: string;
  label_fr: string;
}

interface BackendArtisanTrade {
  trade: BackendTrade;
  hourly_rate_fcfa: number;
  service_radius_m: number;
  has_custom_service_area: boolean;
}

type VerifiedStatus = 'none' | 'pending' | 'verified' | 'rejected';

interface BackendArtisanListItem {
  id: string;
  full_name: string;
  avatar_url: string | null;
  bio: string | null;
  years_experience: number | null;
  is_available: boolean;
  verified_status: VerifiedStatus;
  rating_avg: number | null;
  review_count: number;
  distance_m: number | null;
  trades: BackendArtisanTrade[];
}

interface BackendArtisanDetail extends BackendArtisanListItem {
  cover_url: string | null;
}

interface BackendArtisanStatsPublic {
  rating_avg: number | null;
  review_count: number;
  interventions_count: number;
  response_rate: number | null;
}

// `GET /artisans/{id}/stats` returns this wider shape instead when the
// caller is the artisan owner or an admin (app/schemas/artisans.py
// ArtisanStatsPrivateOut) -- `revenue_fcfa` is absent entirely from the
// JSON body otherwise, never sent as `null` (BUILD_PLAN.md §5 Lot 9).
interface BackendArtisanStatsPrivate extends BackendArtisanStatsPublic {
  revenue_fcfa: number;
}

type BackendArtisanStats = BackendArtisanStatsPublic | BackendArtisanStatsPrivate;

interface BackendReview {
  id: string;
  rating: number;
  comment: string;
  author_name: string;
  created_at: string;
}

interface BackendPage<T> {
  items: T[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

interface BackendSuggestedQuote {
  labor_fcfa: number;
  materials_fcfa: number;
  total_fcfa: number;
}

interface BackendTriageResult {
  trade_code: string;
  price_min_fcfa: number;
  price_max_fcfa: number;
  urgency: 'normal' | 'urgent' | 'immediat';
  suggested_quote: BackendSuggestedQuote;
}

interface BackendLocation {
  lat: number;
  lng: number;
}

interface BackendServiceRequest {
  id: string;
  client_id: string;
  trade: BackendTrade;
  description: string;
  photo_url: string | null;
  location: BackendLocation;
  urgency: 'normal' | 'urgent' | 'immediat';
  ai_estimate_min_fcfa: number | null;
  ai_estimate_max_fcfa: number | null;
  status: 'ouverte' | 'en_relation' | 'convertie' | 'annulee' | 'expiree';
  created_at: string;
}

interface BackendQuote {
  id: string;
  labor_fcfa: number;
  materials_fcfa: number;
  total_fcfa: number;
  status: 'propose' | 'accepte' | 'refuse' | 'expire';
  created_at: string;
}

interface BackendIntervention {
  id: string;
  service_request: BackendServiceRequest;
  client_id: string;
  artisan_id: string;
  status: 'proposee' | 'acceptee' | 'en_cours' | 'terminee' | 'annulee' | 'litige';
  commission_rate_bps: number;
  agreed_amount_fcfa: number | null;
  scheduled_at: string | null;
  completed_at: string | null;
  decline_reason: string | null;
  quote: BackendQuote | null;
  review: BackendReview | null;
  created_at: string;
}

const REVIEWS_PAGE_SIZE = 20;

// The backend's closed urgency enum (app/models/enums.py) mapped to the
// French adjectives the screen already expects (AIAnalysisResult.urgency).
const URGENCY_LABELS: Record<BackendTriageResult['urgency'], string> = {
  normal: 'normale',
  urgent: 'haute',
  immediat: 'immédiate',
};

// A plain space, not `toLocaleString('fr-FR')`'s narrow no-break space
// (U+202F) — matches the literal thousands-separator style already used for
// this string elsewhere in the codebase (mock.ts's fallback defaults).
function formatFcfaThousands(n: number): string {
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

function formatPriceRangeFcfa(minFcfa: number, maxFcfa: number): string {
  return `${formatFcfaThousands(minFcfa)} – ${formatFcfaThousands(maxFcfa)} FCFA`;
}

function formatDistanceM(distanceM: number): string {
  if (distanceM < 1000) return `${Math.round(distanceM)} m`;
  return `${(distanceM / 1000).toFixed(1)} km`;
}

function formatRelativeDate(iso: string): string {
  const then = new Date(iso).getTime();
  const diffDays = Math.floor((Date.now() - then) / (24 * 60 * 60 * 1000));
  if (diffDays <= 0) return "Aujourd'hui";
  if (diffDays === 1) return 'Hier';
  if (diffDays < 7) return `Il y a ${diffDays} jours`;
  if (diffDays < 30) return `Il y a ${Math.floor(diffDays / 7)} semaine(s)`;
  return `Il y a ${Math.floor(diffDays / 30)} mois`;
}

function initialsFrom(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

function mapReview(review: BackendReview): Review {
  return {
    id: review.id,
    author: review.author_name,
    avatarInitials: initialsFrom(review.author_name),
    rating: review.rating,
    date: formatRelativeDate(review.created_at),
    comment: review.comment,
  };
}

function mapServiceRequest(request: BackendServiceRequest): ServiceRequest {
  return {
    id: request.id,
    tradeCode: request.trade.code,
    tradeLabel: request.trade.label_fr,
    description: request.description,
    photoUrl: request.photo_url,
    location: { lat: request.location.lat, lng: request.location.lng },
    urgency: request.urgency,
    aiEstimateMinFcfa: request.ai_estimate_min_fcfa,
    aiEstimateMaxFcfa: request.ai_estimate_max_fcfa,
    status: request.status,
    createdAt: request.created_at,
  };
}

function mapQuote(quote: BackendQuote): Quote {
  return {
    id: quote.id,
    laborFcfa: quote.labor_fcfa,
    materialsFcfa: quote.materials_fcfa,
    totalFcfa: quote.total_fcfa,
    status: quote.status,
    createdAt: quote.created_at,
  };
}

function mapIntervention(intervention: BackendIntervention): Intervention {
  return {
    id: intervention.id,
    serviceRequest: mapServiceRequest(intervention.service_request),
    clientId: intervention.client_id,
    artisanId: intervention.artisan_id,
    status: intervention.status,
    commissionRateBps: intervention.commission_rate_bps,
    agreedAmountFcfa: intervention.agreed_amount_fcfa,
    scheduledAt: intervention.scheduled_at,
    completedAt: intervention.completed_at,
    declineReason: intervention.decline_reason,
    quote: intervention.quote ? mapQuote(intervention.quote) : null,
    review: intervention.review ? mapReview(intervention.review) : null,
    createdAt: intervention.created_at,
  };
}

function mapArtisan(item: BackendArtisanListItem & { cover_url?: string | null }, reviews: Review[]): Artisan {
  const primaryTrade = item.trades[0]?.trade.label_fr ?? '';
  return {
    id: item.id,
    name: item.full_name,
    trade: primaryTrade,
    avatarUrl: item.avatar_url,
    coverUrl: item.cover_url ?? null,
    verified: item.verified_status === 'verified',
    // rating_avg is null when an artisan has no published review yet (real
    // seed data includes such a case) — 0 is the closest honest numeric
    // default for a `number` field; screens don't yet distinguish "unrated"
    // from "rated zero" (pre-existing UI limitation, not introduced here).
    rating: item.rating_avg ?? 0,
    reviewCount: item.review_count,
    // No `near` supplied (no geolocation wired into search yet) -> null on
    // the backend -> blank rather than an invented distance.
    distance: item.distance_m != null ? formatDistanceM(item.distance_m) : '',
    // No reverse-geocoding available from a geography point -> a neutral,
    // still-true-today constant rather than a fabricated address.
    location: 'Dakar, Sénégal',
    // No public hourly/base price exposed by the backend (Lot 9 schemas) ->
    // neutral copy instead of inventing a number.
    priceBase: 'Tarif sur devis',
    priceNumber: 0,
    tags: item.trades.map((t) => t.trade.label_fr),
    bio: item.bio ?? '',
    stats: {
      // review_count is the closest public proxy for "chantiers réalisés" the
      // backend exposes today.
      chantiers: String(item.review_count),
      // response_rate is always null in this backend lot (no responded_at
      // tracking yet, BUILD_PLAN.md Lot 9) -> honest "not available" copy.
      responseTime: 'Non communiqué',
      experience: item.years_experience != null ? `${item.years_experience} ans` : 'Non communiqué',
    },
    realisations: [],
    reviews,
    available: item.is_available,
  };
}

function mapArtisanStats(stats: BackendArtisanStats): ArtisanStats {
  return {
    ratingAvg: stats.rating_avg,
    reviewCount: stats.review_count,
    interventionsCount: stats.interventions_count,
    responseRate: stats.response_rate,
    revenueFcfa: 'revenue_fcfa' in stats ? stats.revenue_fcfa : null,
  };
}

function mapTrade(trade: BackendTrade): Trade {
  return { id: trade.id, code: trade.code, labelFr: trade.label_fr };
}

function buildArtisanQuery(filters?: ArtisanFilters): string {
  const params = new URLSearchParams();
  if (filters?.trade) params.set('trade', filters.trade);
  if (filters?.search) params.set('q', filters.search);
  if (typeof filters?.minRating === 'number') params.set('min_rating', String(filters.minRating));
  if (filters?.near) params.set('near', `${filters.near.lat},${filters.near.lng}`);
  if (typeof filters?.radiusM === 'number') params.set('radius_m', String(filters.radiusM));
  if (typeof filters?.available === 'boolean') params.set('available', String(filters.available));
  if (filters?.sort) params.set('sort', filters.sort);
  if (typeof filters?.page === 'number') params.set('page', String(filters.page));
  if (typeof filters?.pageSize === 'number') params.set('page_size', String(filters.pageSize));
  const query = params.toString();
  return query ? `?${query}` : '';
}

async function fetchArtisanReviews(artisanId: string): Promise<Review[]> {
  const page = await apiRequest<BackendPage<BackendReview>>(
    `/artisans/${artisanId}/reviews?page=1&page_size=${REVIEWS_PAGE_SIZE}`,
  );
  return page.items.map(mapReview);
}

export const httpApiClient: Pick<
  ApiClient,
  | 'listArtisans'
  | 'getArtisanById'
  | 'listTrades'
  | 'analyzeProblem'
  | 'createServiceRequest'
  | 'listMyServiceRequests'
  | 'listMyInterventions'
  | 'getInterventionById'
  | 'acceptIntervention'
  | 'declineIntervention'
  | 'createQuote'
  | 'acceptQuote'
  | 'refuseQuote'
  | 'completeIntervention'
  | 'createReview'
  | 'getArtisanStats'
  | 'updateArtisanAvailability'
> = {
  async listArtisans(filters?: ArtisanFilters): Promise<Artisan[]> {
    const page = await apiRequest<BackendPage<BackendArtisanListItem>>(
      `/artisans${buildArtisanQuery(filters)}`,
    );
    return page.items.map((item) => mapArtisan(item, []));
  },

  async getArtisanById(id: string): Promise<Artisan> {
    // A 404 here already carries the backend's own French, display-ready
    // message (BUILD_PLAN.md §3.1) — propagated as-is by apiRequest, not
    // rewritten here.
    const detail = await apiRequest<BackendArtisanDetail>(`/artisans/${id}`);
    const reviews = await fetchArtisanReviews(id);
    return mapArtisan(detail, reviews);
  },

  async getArtisanStats(artisanId: string): Promise<ArtisanStats> {
    const stats = await apiRequest<BackendArtisanStats>(`/artisans/${artisanId}/stats`);
    return mapArtisanStats(stats);
  },

  async updateArtisanAvailability(isAvailable: boolean): Promise<Artisan> {
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me', {
      method: 'PATCH',
      body: { is_available: isAvailable },
    });
    return mapArtisan(detail, []);
  },

  async listTrades(): Promise<Trade[]> {
    const trades = await apiRequest<BackendTrade[]>('/trades');
    return trades.map(mapTrade);
  },

  // Migration of the old Express /api/analyze-problem (Lot 11, BUILD_PLAN.md
  // SS3.2, SS6): the backend now validates the AI output strictly (schema,
  // amounts, trade_code existence) and always falls back to a heuristic
  // rather than erroring, so this call never needs its own try/catch beyond
  // what apiRequest already provides.
  async analyzeProblem(description: string): Promise<AIAnalysisResult> {
    const [result, trades] = await Promise.all([
      apiRequest<BackendTriageResult>('/ai/analyze', {
        method: 'POST',
        body: { description },
      }),
      apiRequest<BackendTrade[]>('/trades').then((list) => list.map(mapTrade)),
    ]);

    // trade_code is guaranteed to reference an active trade by the backend
    // (app.services.ai_triage) -- falling back to the raw code here only
    // guards against a race with a trade deactivated between the two calls.
    const tradeLabel = trades.find((t) => t.code === result.trade_code)?.labelFr ?? result.trade_code;

    return {
      trade: tradeLabel,
      tradeCode: result.trade_code,
      priceEstimate: formatPriceRangeFcfa(result.price_min_fcfa, result.price_max_fcfa),
      priceMinFcfa: result.price_min_fcfa,
      priceMaxFcfa: result.price_max_fcfa,
      recommendedCount: 3,
      explanation:
        "L'IA a analysé votre description pour identifier les meilleurs experts disponibles immédiatement à Dakar.",
      urgency: URGENCY_LABELS[result.urgency],
      urgencyCode: result.urgency,
      suggestedDevis: {
        title: tradeLabel,
        labor: result.suggested_quote.labor_fcfa,
        materials: result.suggested_quote.materials_fcfa,
        total: result.suggested_quote.total_fcfa,
      },
    };
  },

  async createServiceRequest(input: CreateServiceRequestInput): Promise<ServiceRequest> {
    const request = await apiRequest<BackendServiceRequest>('/requests', {
      method: 'POST',
      body: {
        trade_code: input.tradeCode,
        description: input.description,
        photo_url: input.photoUrl ?? null,
        location: input.location,
        urgency: input.urgency,
        ai_estimate_min_fcfa: input.aiEstimateMinFcfa ?? null,
        ai_estimate_max_fcfa: input.aiEstimateMaxFcfa ?? null,
      },
    });
    return mapServiceRequest(request);
  },

  async listMyServiceRequests(): Promise<ServiceRequest[]> {
    const page = await apiRequest<BackendPage<BackendServiceRequest>>('/requests/me');
    return page.items.map(mapServiceRequest);
  },

  async listMyInterventions(): Promise<Intervention[]> {
    const page = await apiRequest<BackendPage<BackendIntervention>>('/interventions/me');
    return page.items.map(mapIntervention);
  },

  async getInterventionById(id: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}`);
    return mapIntervention(intervention);
  },

  async acceptIntervention(id: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/accept`, {
      method: 'POST',
    });
    return mapIntervention(intervention);
  },

  async declineIntervention(id: string, reason?: string | null): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/decline`, {
      method: 'POST',
      body: { reason: reason ?? null },
    });
    return mapIntervention(intervention);
  },

  async createQuote(interventionId: string, input: CreateQuoteInput): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/interventions/${interventionId}/quote`,
      { method: 'POST', body: { labor_fcfa: input.laborFcfa, materials_fcfa: input.materialsFcfa } },
    );
    return mapIntervention(intervention);
  },

  async acceptQuote(interventionId: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/interventions/${interventionId}/quote/accept`,
      { method: 'POST' },
    );
    return mapIntervention(intervention);
  },

  async refuseQuote(interventionId: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/interventions/${interventionId}/quote/refuse`,
      { method: 'POST' },
    );
    return mapIntervention(intervention);
  },

  async completeIntervention(id: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/complete`, {
      method: 'POST',
    });
    return mapIntervention(intervention);
  },

  async createReview(interventionId: string, input: CreateReviewInput): Promise<Review> {
    const review = await apiRequest<BackendReview>(`/interventions/${interventionId}/review`, {
      method: 'POST',
      body: { rating: input.rating, comment: input.comment },
    });
    return mapReview(review);
  },
};
