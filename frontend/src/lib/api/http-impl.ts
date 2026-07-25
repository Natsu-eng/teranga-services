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
import type { AIAnalysisResult, Artisan, Review, ServiceRequest, Trade } from '../../types';
import { apiRequest } from './http';
import type { ApiClient, ArtisanFilters, CreateServiceRequestInput } from './types';

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
};
