/**
 * Implémentation HTTP — et seule implémentation de production — de
 * `ApiClient`, adossée au backend FastAPI. Couvre le contrat EN ENTIER
 * (typé `ApiClient`, pas un sous-ensemble) : voir index.ts.
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
  AdminVerificationListItem,
  ChatMessage,
  ConversationDetail,
  ConversationParticipant,
  ConversationSummary,
  MessageHistory,
  AdminVerificationReview,
  AIAnalysisResult,
  Artisan,
  ArtisanStats,
  ArtisanEarnings,
  ArtisanTradeDetail,
  Cancellation,
  ClientPayment,
  EngagementBlocker,
  EngagementCheck,
  RequestEligibility,
  Dispute,
  Intervention,
  MyArtisanProfile,
  MyReceivedReview,
  PaymentChannel,
  PaymentOptions,
  PaymentStatus,
  PaymentSummary,
  PayoutChannel,
  PayoutSettings,
  PayoutStatus,
  PlatformFeeStatus,
  MyVerification,
  ProfileMediaConstraints,
  Quote,
  Review,
  ServiceRequest,
  Trade,
  VerificationDocType,
  VerificationDocument,
} from '../../types';
import { apiRequest, apiRequestBlob } from './http';
import { httpAdminBackoffice } from './admin-backoffice';
import { ApiError } from './types';
import type {
  AddArtisanTradeInput,
  AdminVerificationFilters,
  ApiClient,
  ArtisanFilters,
  ConversationFilters,
  CreateInterventionInput,
  CreateQuoteInput,
  MessageCursor,
  RealtimeTicket,
  CreateReviewInput,
  CreateServiceRequestInput,
  UpdateArtisanProfileInput,
} from './types';
import { formatFcfa } from '../format';
import { initialsFrom } from '../initials';

interface BackendTrade {
  id: string;
  code: string;
  label_fr: string;
}

interface BackendArtisanTrade {
  id: string;
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
  is_suspended: boolean;
  // Renseigné seulement pour l'artisan lui-même et l'admin : la fiche d'un
  // suspendu n'est jamais servie au public.
  suspension_reason: string | null;
}

interface BackendMediaUploadLimits {
  max_upload_bytes: number;
  max_side_px: number;
}

interface BackendProfileMediaConstraints {
  accepted_mime_types: string[];
  max_pixels: number;
  avatar: BackendMediaUploadLimits;
  cover: BackendMediaUploadLimits;
}

interface BackendVerificationDocument {
  id: string;
  doc_type: VerificationDocType;
  status: 'pending' | 'approved' | 'rejected';
  note: string | null;
  created_at: string;
  reviewed_at: string | null;
}

interface BackendMyVerification {
  verified_status: VerifiedStatus;
  documents: BackendVerificationDocument[];
}

interface BackendAdminVerificationListItem {
  id: string;
  artisan_id: string;
  artisan_full_name: string;
  doc_type: VerificationDocType;
  status: 'pending' | 'approved' | 'rejected';
  note: string | null;
  created_at: string;
  reviewed_at: string | null;
}

interface BackendAdminVerificationReview {
  id: string;
  doc_type: VerificationDocType;
  status: 'pending' | 'approved' | 'rejected';
  note: string | null;
  reviewed_by: string;
  reviewed_at: string;
  artisan_id: string;
  artisan_verified_status: VerifiedStatus;
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
  status: 'publie' | 'masque' | 'signale';
}

interface BackendMyReceivedReview extends BackendReview {
  report_reason: string | null;
  reported_at: string | null;
  can_report: boolean;
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
  location_label?: string | null;
  urgency: 'normal' | 'urgent' | 'immediat';
  ai_estimate_min_fcfa: number | null;
  ai_estimate_max_fcfa: number | null;
  status: 'ouverte' | 'en_relation' | 'convertie' | 'annulee' | 'expiree';
  expires_at?: string | null;
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
  cancellation?: BackendCancellation | null;
  quote: BackendQuote | null;
  review: BackendReview | null;
  conversation_id?: string | null;
  payment?: BackendPaymentSummary | null;
  dispute?: BackendDispute | null;
  created_at: string;
}

interface BackendCancellation {
  kind: Cancellation['kind'];
  by: Cancellation['by'];
  reason: string | null;
  at: string;
}

interface BackendDispute {
  opened_by: Dispute['openedBy'];
  reason: string;
  opened_at: string;
  outcome: Dispute['outcome'];
  resolved_at: string | null;
  resolution_note: string | null;
}

interface BackendPaymentSummary {
  amount_fcfa: number;
  commission: { rate_bps: number; amount_fcfa: number; status: PlatformFeeStatus | null };
  net_fcfa: number;
  status: PaymentStatus | null;
  channel: PaymentChannel | null;
  checkout_url: string | null;
  checkout_expires_at: string | null;
  paid_at: string | null;
  released_at: string | null;
  refunded_at: string | null;
  payout: {
    status: PayoutStatus;
    amount_fcfa: number;
    channel: PayoutChannel;
    sent_at: string | null;
  } | null;
}

interface BackendClientPayment {
  id: string;
  intervention_id: string;
  trade_label: string;
  artisan_name: string;
  amount_fcfa: number;
  channel: PaymentChannel;
  status: PaymentStatus;
  created_at: string;
  paid_at: string | null;
  released_at: string | null;
  refunded_at: string | null;
}

interface BackendEarnings {
  totals: {
    paid_out_fcfa: number;
    payout_pending_fcfa: number;
    in_escrow_fcfa: number;
    commission_collected_fcfa: number;
    cash_received_fcfa: number;
    commission_due_fcfa: number;
  };
  items: {
    intervention_id: string;
    trade_label: string;
    client_name: string;
    intervention_status: BackendIntervention['status'];
    payment: BackendPaymentSummary;
  }[];
}

interface BackendPayoutSettings {
  channel: PayoutChannel;
  chosen: boolean;
  allowed_channels: PayoutChannel[];
  destination_phone: string;
}

interface BackendChatMessage {
  id: string;
  conversation_id: string;
  seq: number;
  sender_id: string;
  body: string;
  contact_masked: boolean;
  has_attachment: boolean;
  attachment_content_type: string | null;
  created_at: string;
}

interface BackendParticipant {
  user_id: string;
  role: 'client' | 'artisan';
  display_name: string;
  avatar_url: string | null;
  artisan_profile_id: string | null;
}

interface BackendConversationSummary {
  id: string;
  intervention_id: string | null;
  intervention_status: BackendIntervention['status'] | null;
  trade_label: string | null;
  other_party: BackendParticipant;
  last_message: {
    body: string;
    from_me: boolean;
    has_attachment: boolean;
    created_at: string;
  } | null;
  unread_count: number;
  last_activity_at: string;
}

interface BackendConversation {
  id: string;
  intervention_id: string | null;
  intervention_status: BackendIntervention['status'] | null;
  trade_label: string | null;
  other_party: BackendParticipant;
  my_last_read_seq: number;
  can_send: boolean;
  created_at: string;
}

const REVIEWS_PAGE_SIZE = 20;
// Avis reçus affichés dans l'espace Pro (plafond serveur : PAGINATION_PAGE_SIZE_MAX).
const MY_REVIEWS_PAGE_SIZE = 50;

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
  return Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
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

function mapReview(review: BackendReview): Review {
  return {
    id: review.id,
    author: review.author_name,
    avatarInitials: initialsFrom(review.author_name),
    rating: review.rating,
    date: formatRelativeDate(review.created_at),
    comment: review.comment,
    moderationStatus: review.status,
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
    locationLabel: request.location_label ?? null,
    urgency: request.urgency,
    aiEstimateMinFcfa: request.ai_estimate_min_fcfa,
    aiEstimateMaxFcfa: request.ai_estimate_max_fcfa,
    status: request.status,
    expiresAt: request.expires_at ?? null,
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

function mapPaymentSummary(payment: BackendPaymentSummary): PaymentSummary {
  return {
    amountFcfa: payment.amount_fcfa,
    commission: {
      rateBps: payment.commission.rate_bps,
      amountFcfa: payment.commission.amount_fcfa,
      status: payment.commission.status,
    },
    netFcfa: payment.net_fcfa,
    status: payment.status,
    channel: payment.channel,
    checkoutUrl: payment.checkout_url,
    checkoutExpiresAt: payment.checkout_expires_at,
    paidAt: payment.paid_at,
    releasedAt: payment.released_at,
    refundedAt: payment.refunded_at,
    payout: payment.payout
      ? {
          status: payment.payout.status,
          amountFcfa: payment.payout.amount_fcfa,
          channel: payment.payout.channel,
          sentAt: payment.payout.sent_at,
        }
      : null,
  };
}

function mapPayoutSettings(settings: BackendPayoutSettings): PayoutSettings {
  return {
    channel: settings.channel,
    chosen: settings.chosen,
    allowedChannels: settings.allowed_channels,
    destinationPhone: settings.destination_phone,
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
    cancellation: intervention.cancellation ? { ...intervention.cancellation } : null,
    quote: intervention.quote ? mapQuote(intervention.quote) : null,
    review: intervention.review ? mapReview(intervention.review) : null,
    conversationId: intervention.conversation_id ?? null,
    payment: intervention.payment ? mapPaymentSummary(intervention.payment) : null,
    dispute: intervention.dispute
      ? {
          openedBy: intervention.dispute.opened_by,
          reason: intervention.dispute.reason,
          openedAt: intervention.dispute.opened_at,
          outcome: intervention.dispute.outcome,
          resolvedAt: intervention.dispute.resolved_at,
          resolutionNote: intervention.dispute.resolution_note,
        }
      : null,
    createdAt: intervention.created_at,
  };
}

/**
 * Message reçu du serveur, par REST comme par le canal temps réel (même
 * forme) -- exporté pour que la couche temps réel n'en ait pas sa copie.
 */
export function mapChatMessage(message: BackendChatMessage): ChatMessage {
  return {
    id: message.id,
    conversationId: message.conversation_id,
    seq: message.seq,
    senderId: message.sender_id,
    body: message.body,
    contactMasked: message.contact_masked,
    hasAttachment: message.has_attachment,
    attachmentContentType: message.attachment_content_type,
    createdAt: message.created_at,
  };
}

/** Forme brute d'un message tel qu'émis par le serveur (REST et temps réel). */
export type { BackendChatMessage };

function mapParticipant(participant: BackendParticipant): ConversationParticipant {
  return {
    userId: participant.user_id,
    role: participant.role,
    displayName: participant.display_name,
    avatarUrl: participant.avatar_url,
    artisanProfileId: participant.artisan_profile_id,
  };
}

function mapConversationSummary(summary: BackendConversationSummary): ConversationSummary {
  return {
    id: summary.id,
    interventionId: summary.intervention_id,
    interventionStatus: summary.intervention_status,
    tradeLabel: summary.trade_label,
    otherParty: mapParticipant(summary.other_party),
    lastMessage: summary.last_message
      ? {
          body: summary.last_message.body,
          fromMe: summary.last_message.from_me,
          hasAttachment: summary.last_message.has_attachment,
          createdAt: summary.last_message.created_at,
        }
      : null,
    unreadCount: summary.unread_count,
    lastActivityAt: summary.last_activity_at,
  };
}

function mapConversation(conversation: BackendConversation): ConversationDetail {
  return {
    id: conversation.id,
    interventionId: conversation.intervention_id,
    interventionStatus: conversation.intervention_status,
    tradeLabel: conversation.trade_label,
    otherParty: mapParticipant(conversation.other_party),
    myLastReadSeq: conversation.my_last_read_seq,
    canSend: conversation.can_send,
    createdAt: conversation.created_at,
  };
}

function mapArtisan(
  item: BackendArtisanListItem & { cover_url?: string | null },
  reviews: Review[],
): Artisan {
  const primaryTrade = item.trades[0]?.trade.label_fr ?? '';
  const lowestRate =
    item.trades.length > 0 ? Math.min(...item.trades.map((t) => t.hourly_rate_fcfa)) : null;
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
    // Prix indicatif réel : le tarif horaire le plus bas parmi les métiers
    // déclarés (`hourly_rate_fcfa`, exposé publiquement par ArtisanTradeOut).
    // Sans métier déclaré, une mention neutre plutôt qu'un montant inventé.
    priceBase: lowestRate != null ? `Dès ${formatFcfa(lowestRate)}/h` : 'Tarif sur devis',
    priceNumber: lowestRate ?? 0,
    tags: item.trades.map((t) => t.trade.label_fr),
    tradeCodes: item.trades.map((t) => t.trade.code),
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

function mapArtisanTradeDetail(item: BackendArtisanTrade): ArtisanTradeDetail {
  return {
    id: item.id,
    tradeCode: item.trade.code,
    tradeLabel: item.trade.label_fr,
    hourlyRateFcfa: item.hourly_rate_fcfa,
    serviceRadiusM: item.service_radius_m,
    hasCustomServiceArea: item.has_custom_service_area,
  };
}

function mapMyArtisanProfile(item: BackendArtisanDetail): MyArtisanProfile {
  return {
    id: item.id,
    fullName: item.full_name,
    bio: item.bio,
    yearsExperience: item.years_experience,
    avatarUrl: item.avatar_url,
    coverUrl: item.cover_url,
    isAvailable: item.is_available,
    verifiedStatus: item.verified_status,
    trades: item.trades.map(mapArtisanTradeDetail),
    isSuspended: item.is_suspended,
    suspensionReason: item.suspension_reason,
  };
}

function mapMyReceivedReview(review: BackendMyReceivedReview): MyReceivedReview {
  return {
    id: review.id,
    rating: review.rating,
    comment: review.comment,
    authorName: review.author_name,
    createdAt: review.created_at,
    status: review.status,
    reportReason: review.report_reason,
    reportedAt: review.reported_at,
    canReport: review.can_report,
  };
}

function mapMediaUploadLimits(limits: BackendMediaUploadLimits) {
  return { maxUploadBytes: limits.max_upload_bytes, maxSidePx: limits.max_side_px };
}

function mapProfileMediaConstraints(item: BackendProfileMediaConstraints): ProfileMediaConstraints {
  return {
    acceptedMimeTypes: item.accepted_mime_types,
    maxPixels: item.max_pixels,
    avatar: mapMediaUploadLimits(item.avatar),
    cover: mapMediaUploadLimits(item.cover),
  };
}

function mapVerificationDocument(item: BackendVerificationDocument): VerificationDocument {
  return {
    id: item.id,
    docType: item.doc_type,
    status: item.status,
    note: item.note,
    createdAt: item.created_at,
    reviewedAt: item.reviewed_at,
  };
}

function mapMyVerification(item: BackendMyVerification): MyVerification {
  return {
    verifiedStatus: item.verified_status,
    documents: item.documents.map(mapVerificationDocument),
  };
}

function mapAdminVerificationListItem(
  item: BackendAdminVerificationListItem,
): AdminVerificationListItem {
  return {
    id: item.id,
    artisanId: item.artisan_id,
    artisanFullName: item.artisan_full_name,
    docType: item.doc_type,
    status: item.status,
    note: item.note,
    createdAt: item.created_at,
    reviewedAt: item.reviewed_at,
  };
}

function mapAdminVerificationReview(item: BackendAdminVerificationReview): AdminVerificationReview {
  return {
    id: item.id,
    docType: item.doc_type,
    status: item.status,
    note: item.note,
    reviewedBy: item.reviewed_by,
    reviewedAt: item.reviewed_at,
    artisanId: item.artisan_id,
    artisanVerifiedStatus: item.artisan_verified_status,
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

/**
 * À utiliser pour toute méthode d'`ApiClient` déclarée avant que le backend
 * ne la serve : échoue explicitement avec un code dédié (`not_implemented`)
 * et un message affichable, au lieu de renvoyer des données inventées.
 */
export function notImplemented(feature: string): never {
  throw new ApiError(
    'not_implemented',
    `${feature} n'est pas encore disponible. Merci de réessayer plus tard.`,
  );
}

export const httpApiClient: ApiClient = {
  ...httpAdminBackoffice,

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

  async getMyArtisanProfile(artisanId: string): Promise<MyArtisanProfile> {
    const detail = await apiRequest<BackendArtisanDetail>(`/artisans/${artisanId}`);
    return mapMyArtisanProfile(detail);
  },

  async updateMyArtisanProfile(input: UpdateArtisanProfileInput): Promise<MyArtisanProfile> {
    // Seuls les champs réellement fournis par l'appelant sont envoyés --
    // reflète la sémantique de mise à jour partielle du backend
    // (`exclude_unset`, app/schemas/artisans.py ArtisanProfileUpdateIn) :
    // omettre un champ ici ne doit jamais être interprété comme "l'effacer"
    // côté serveur.
    const body: Record<string, unknown> = {};
    if (input.fullName !== undefined) body.full_name = input.fullName;
    if (input.bio !== undefined) body.bio = input.bio;
    if (input.yearsExperience !== undefined) body.years_experience = input.yearsExperience;
    if (input.baseLocation !== undefined) body.base_location = input.baseLocation;
    if (input.avatarUrl !== undefined) body.avatar_url = input.avatarUrl;
    if (input.coverUrl !== undefined) body.cover_url = input.coverUrl;
    if (input.isAvailable !== undefined) body.is_available = input.isAvailable;

    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me', {
      method: 'PATCH',
      body,
    });
    return mapMyArtisanProfile(detail);
  },

  async uploadAvatar(file: File): Promise<MyArtisanProfile> {
    const formData = new FormData();
    formData.set('file', file);
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me/avatar', {
      method: 'POST',
      formData,
    });
    return mapMyArtisanProfile(detail);
  },

  // Même contrat que uploadAvatar (multipart `file`, profil complet en
  // retour) -- budget d'envois partagé avec l'avatar côté serveur : un 429
  // remonte avec le message français du backend, affiché tel quel.
  async uploadCover(file: File): Promise<MyArtisanProfile> {
    const formData = new FormData();
    formData.set('file', file);
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me/cover', {
      method: 'POST',
      formData,
    });
    return mapMyArtisanProfile(detail);
  },

  async getProfileMediaConstraints(): Promise<ProfileMediaConstraints> {
    const body = await apiRequest<BackendProfileMediaConstraints>('/artisans/me/media-constraints');
    return mapProfileMediaConstraints(body);
  },

  async addArtisanTrade(input: AddArtisanTradeInput): Promise<MyArtisanProfile> {
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me/trades', {
      method: 'POST',
      body: {
        trade_code: input.tradeCode,
        hourly_rate_fcfa: input.hourlyRateFcfa,
        service_radius_m: input.serviceRadiusM,
      },
    });
    return mapMyArtisanProfile(detail);
  },

  async removeArtisanTrade(artisanTradeId: string): Promise<MyArtisanProfile> {
    const detail = await apiRequest<BackendArtisanDetail>(`/artisans/me/trades/${artisanTradeId}`, {
      method: 'DELETE',
    });
    return mapMyArtisanProfile(detail);
  },

  async listMyVerificationDocuments(): Promise<MyVerification> {
    const body = await apiRequest<BackendMyVerification>('/artisans/me/documents');
    return mapMyVerification(body);
  },

  async uploadVerificationDocument(
    docType: VerificationDocType,
    file: File,
  ): Promise<VerificationDocument> {
    const formData = new FormData();
    formData.set('doc_type', docType);
    formData.set('file', file);
    const document = await apiRequest<BackendVerificationDocument>('/artisans/me/documents', {
      method: 'POST',
      formData,
    });
    return mapVerificationDocument(document);
  },

  async listAdminVerifications(
    filters?: AdminVerificationFilters,
  ): Promise<AdminVerificationListItem[]> {
    const params = new URLSearchParams();
    if (filters?.status) params.set('status', filters.status);
    // Grande page unique plutôt qu'une pagination -- une file d'attente de
    // revue admin (BUILD_PLAN.md) n'est pas censée accumuler des centaines
    // d'éléments en attente ; si ça arrivait un jour, ce serait un signal
    // opérationnel à traiter avant d'ajouter une UI de pagination.
    params.set('page_size', '100');
    const page = await apiRequest<BackendPage<BackendAdminVerificationListItem>>(
      `/admin/verifications?${params.toString()}`,
    );
    return page.items.map(mapAdminVerificationListItem);
  },

  async getAdminVerificationDocumentBlob(verificationId: string): Promise<Blob> {
    return apiRequestBlob(`/admin/verifications/${verificationId}/content`);
  },

  async approveVerification(verificationId: string): Promise<AdminVerificationReview> {
    const review = await apiRequest<BackendAdminVerificationReview>(
      `/admin/verifications/${verificationId}/approve`,
      { method: 'POST' },
    );
    return mapAdminVerificationReview(review);
  },

  async rejectVerification(verificationId: string, note: string): Promise<AdminVerificationReview> {
    const review = await apiRequest<BackendAdminVerificationReview>(
      `/admin/verifications/${verificationId}/reject`,
      { method: 'POST', body: { note } },
    );
    return mapAdminVerificationReview(review);
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
    const tradeLabel =
      trades.find((t) => t.code === result.trade_code)?.labelFr ?? result.trade_code;

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
        location_label: input.locationLabel,
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

  async cancelServiceRequest(requestId: string): Promise<ServiceRequest> {
    const request = await apiRequest<BackendServiceRequest>(
      `/requests/${encodeURIComponent(requestId)}/cancel`,
      { method: 'POST' },
    );
    return mapServiceRequest(request);
  },

  async listRequestEligibility(artisanId: string): Promise<RequestEligibility[]> {
    const items = await apiRequest<
      { request_id: string; eligible: boolean; reason: EngagementBlocker | null }[]
    >(`/requests/me/eligibility?artisan_id=${encodeURIComponent(artisanId)}`);
    return items.map((item) => ({
      requestId: item.request_id,
      eligible: item.eligible,
      reason: item.reason,
    }));
  },

  async checkArtisanCoverage(
    artisanId: string,
    tradeCode: string,
    location: { lat: number; lng: number },
  ): Promise<EngagementCheck> {
    const params = new URLSearchParams({
      trade: tradeCode,
      lat: String(location.lat),
      lng: String(location.lng),
    });
    return apiRequest<EngagementCheck>(
      `/artisans/${encodeURIComponent(artisanId)}/coverage?${params.toString()}`,
    );
  },

  async listMyInterventions(): Promise<Intervention[]> {
    const page = await apiRequest<BackendPage<BackendIntervention>>('/interventions/me');
    return page.items.map(mapIntervention);
  },

  /**
   * Mise en relation : propose une demande ouverte du client à un artisan
   * (`POST /interventions`). Le serveur vérifie tout — demande ouverte et
   * appartenant au client, artisan vérifié, métier exercé, zone couverte —
   * et renvoie un message affichable en cas de refus.
   */
  async createIntervention(input: CreateInterventionInput): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>('/interventions', {
      method: 'POST',
      body: { service_request_id: input.serviceRequestId, artisan_id: input.artisanId },
    });
    return mapIntervention(intervention);
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
      {
        method: 'POST',
        body: { labor_fcfa: input.laborFcfa, materials_fcfa: input.materialsFcfa },
      },
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

  async cancelIntervention(id: string, reason?: string | null): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/cancel`, {
      method: 'POST',
      body: { reason: reason ?? null },
    });
    return mapIntervention(intervention);
  },

  async openDispute(id: string, reason: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/dispute`, {
      method: 'POST',
      body: { reason },
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

  // ------------------------------------------------------------- Messagerie

  async listConversations(filters?: ConversationFilters): Promise<ConversationSummary[]> {
    const params = new URLSearchParams({ page_size: '50' });
    if (filters?.artisanId) params.set('artisan_id', filters.artisanId);
    const page = await apiRequest<BackendPage<BackendConversationSummary>>(
      `/conversations/me?${params.toString()}`,
    );
    return page.items.map(mapConversationSummary);
  },

  async getUnreadMessageCount(): Promise<number> {
    const result = await apiRequest<{ count: number }>('/conversations/me/unread-count');
    return result.count;
  },

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    return mapConversation(
      await apiRequest<BackendConversation>(`/conversations/${conversationId}`),
    );
  },

  async listMessages(conversationId: string, cursor?: MessageCursor): Promise<MessageHistory> {
    const params = new URLSearchParams();
    if (cursor?.before !== undefined) params.set('before', String(cursor.before));
    if (cursor?.since !== undefined) params.set('since', String(cursor.since));
    if (cursor?.limit !== undefined) params.set('limit', String(cursor.limit));
    const query = params.toString();
    const history = await apiRequest<{ items: BackendChatMessage[]; has_more: boolean }>(
      `/conversations/${conversationId}/messages${query ? `?${query}` : ''}`,
    );
    return { items: history.items.map(mapChatMessage), hasMore: history.has_more };
  },

  async sendMessage(conversationId: string, body: string): Promise<ChatMessage> {
    return mapChatMessage(
      await apiRequest<BackendChatMessage>(`/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: { body },
      }),
    );
  },

  async sendImageMessage(
    conversationId: string,
    file: File,
    caption: string,
  ): Promise<ChatMessage> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('caption', caption);
    return mapChatMessage(
      await apiRequest<BackendChatMessage>(`/conversations/${conversationId}/messages/image`, {
        method: 'POST',
        formData,
      }),
    );
  },

  async markConversationRead(
    conversationId: string,
    lastReadSeq: number,
  ): Promise<ConversationDetail> {
    return mapConversation(
      await apiRequest<BackendConversation>(`/conversations/${conversationId}/read`, {
        method: 'POST',
        body: { last_read_seq: lastReadSeq },
      }),
    );
  },

  async getMessageAttachmentBlob(conversationId: string, messageId: string): Promise<Blob> {
    return apiRequestBlob(`/conversations/${conversationId}/messages/${messageId}/attachment`);
  },

  async createRealtimeTicket(): Promise<RealtimeTicket> {
    const result = await apiRequest<{ ticket: string; expires_in: number }>('/realtime/ticket', {
      method: 'POST',
    });
    return { ticket: result.ticket, expiresIn: result.expires_in };
  },

  async getPaymentOptions(): Promise<PaymentOptions> {
    const options = await apiRequest<{
      online_channels: PaymentChannel[];
      cash_enabled: boolean;
      currency: string;
    }>('/payments/options');
    return {
      onlineChannels: options.online_channels,
      cashEnabled: options.cash_enabled,
      currency: options.currency,
    };
  },

  /**
   * Ouvre le paiement : seul le moyen choisi est envoyé, le MONTANT est
   * celui du devis accepté, fixé par le serveur (jamais transmis d'ici).
   */
  async initPayment(interventionId: string, channel: PaymentChannel): Promise<PaymentSummary> {
    const payment = await apiRequest<BackendPaymentSummary>('/payments/init', {
      method: 'POST',
      body: { intervention_id: interventionId, channel },
    });
    return mapPaymentSummary(payment);
  },

  async listMyPayments(): Promise<ClientPayment[]> {
    const page = await apiRequest<BackendPage<BackendClientPayment>>('/payments/me');
    return page.items.map((payment) => ({
      id: payment.id,
      interventionId: payment.intervention_id,
      tradeLabel: payment.trade_label,
      artisanName: payment.artisan_name,
      amountFcfa: payment.amount_fcfa,
      channel: payment.channel,
      status: payment.status,
      createdAt: payment.created_at,
      paidAt: payment.paid_at,
      releasedAt: payment.released_at,
      refundedAt: payment.refunded_at,
    }));
  },

  async getMyEarnings(): Promise<ArtisanEarnings> {
    const earnings = await apiRequest<BackendEarnings>('/payments/me/earnings');
    return {
      totals: {
        paidOutFcfa: earnings.totals.paid_out_fcfa,
        payoutPendingFcfa: earnings.totals.payout_pending_fcfa,
        inEscrowFcfa: earnings.totals.in_escrow_fcfa,
        commissionCollectedFcfa: earnings.totals.commission_collected_fcfa,
        cashReceivedFcfa: earnings.totals.cash_received_fcfa,
        commissionDueFcfa: earnings.totals.commission_due_fcfa,
      },
      items: earnings.items.map((item) => ({
        interventionId: item.intervention_id,
        tradeLabel: item.trade_label,
        clientName: item.client_name,
        interventionStatus: item.intervention_status,
        payment: mapPaymentSummary(item.payment),
      })),
    };
  },

  async getPayoutSettings(): Promise<PayoutSettings> {
    return mapPayoutSettings(
      await apiRequest<BackendPayoutSettings>('/payments/me/payout-settings'),
    );
  },

  async updatePayoutSettings(channel: PayoutChannel): Promise<PayoutSettings> {
    return mapPayoutSettings(
      await apiRequest<BackendPayoutSettings>('/payments/me/payout-settings', {
        method: 'PUT',
        body: { channel },
      }),
    );
  },

  async listMyReviews(): Promise<MyReceivedReview[]> {
    // Grande page unique : un artisan relit ses avis récents ; l'historique
    // complet reste servi page par page par l'API si besoin.
    const page = await apiRequest<BackendPage<BackendMyReceivedReview>>(
      `/artisans/me/reviews?page=1&page_size=${MY_REVIEWS_PAGE_SIZE}`,
    );
    return page.items.map(mapMyReceivedReview);
  },

  async reportReview(reviewId: string, reason: string): Promise<MyReceivedReview> {
    return mapMyReceivedReview(
      await apiRequest<BackendMyReceivedReview>(`/artisans/me/reviews/${reviewId}/report`, {
        method: 'POST',
        body: { reason },
      }),
    );
  },

  async listAdminDisputes(filters?: { resolved?: boolean }): Promise<Intervention[]> {
    const query = filters?.resolved ? '?resolved=true' : '';
    const page = await apiRequest<BackendPage<BackendIntervention>>(`/admin/disputes${query}`);
    return page.items.map(mapIntervention);
  },

  async resolveDispute(
    interventionId: string,
    outcome: 'libere' | 'rembourse',
    note: string,
  ): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/admin/disputes/${interventionId}/resolve`,
      { method: 'POST', body: { outcome, note } },
    );
    return mapIntervention(intervention);
  },
};
