/**
 * Conversion des réponses du backend vers les types de l'interface
 * (camelCase, libellés français) et formats d'affichage associés.
 * Extraits de `http-impl.ts` sans changement de logique : aucune valeur
 * inventée, un champ absent côté serveur devient un repli neutre.
 */
import type {
  AdminVerificationListItem,
  ChatMessage,
  ConversationDetail,
  ConversationParticipant,
  ConversationSummary,
  AdminVerificationReview,
  Artisan,
  ArtisanStats,
  ArtisanTradeDetail,
  Intervention,
  AdminSupportTicket,
  SupportTicket,
  MyArtisanProfile,
  MyReceivedReview,
  PaymentSummary,
  PayoutSettings,
  MyVerification,
  ProfileMediaConstraints,
  Quote,
  Review,
  ServiceRequest,
  Trade,
  VerificationDocument,
} from '../../types';
import { formatFcfa } from '../format';
import { initialsFrom } from '../initials';
import type {
  BackendAdminVerificationListItem,
  BackendAdminVerificationReview,
  BackendArtisanDetail,
  BackendArtisanListItem,
  BackendArtisanStats,
  BackendArtisanTrade,
  BackendChatMessage,
  BackendConversation,
  BackendConversationSummary,
  BackendIntervention,
  BackendAdminSupportTicket,
  BackendSupportTicket,
  BackendMediaUploadLimits,
  BackendMyReceivedReview,
  BackendMyVerification,
  BackendParticipant,
  BackendPaymentSummary,
  BackendPayoutSettings,
  BackendProfileMediaConstraints,
  BackendQuote,
  BackendReview,
  BackendServiceRequest,
  BackendTrade,
  BackendTriageResult,
  BackendVerificationDocument,
} from './backend-types';

// The backend's closed urgency enum (app/models/enums.py) mapped to the
// French adjectives the screen already expects (AIAnalysisResult.urgency).
export const URGENCY_LABELS: Record<BackendTriageResult['urgency'], string> = {
  normal: 'normale',
  urgent: 'haute',
  immediat: 'immédiate',
};

export function formatDistanceM(distanceM: number): string {
  if (distanceM < 1000) return `${Math.round(distanceM)} m`;
  return `${(distanceM / 1000).toFixed(1)} km`;
}

export function formatRelativeDate(iso: string): string {
  const then = new Date(iso).getTime();
  const diffDays = Math.floor((Date.now() - then) / (24 * 60 * 60 * 1000));
  if (diffDays <= 0) return "Aujourd'hui";
  if (diffDays === 1) return 'Hier';
  if (diffDays < 7) return `Il y a ${diffDays} jours`;
  if (diffDays < 30) return `Il y a ${Math.floor(diffDays / 7)} semaine(s)`;
  return `Il y a ${Math.floor(diffDays / 30)} mois`;
}

export function mapReview(review: BackendReview): Review {
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

export function mapServiceRequest(request: BackendServiceRequest): ServiceRequest {
  return {
    id: request.id,
    tradeCode: request.trade.code,
    tradeLabel: request.trade.label_fr,
    description: request.description,
    photoUrl: request.photo_url,
    location: { lat: request.location.lat, lng: request.location.lng },
    locationLabel: request.location_label ?? null,
    urgency: request.urgency,
    status: request.status,
    expiresAt: request.expires_at ?? null,
    createdAt: request.created_at,
  };
}

export function mapQuote(quote: BackendQuote): Quote {
  return {
    id: quote.id,
    laborFcfa: quote.labor_fcfa,
    materialsFcfa: quote.materials_fcfa,
    totalFcfa: quote.total_fcfa,
    status: quote.status,
    createdAt: quote.created_at,
  };
}

export function mapPaymentSummary(payment: BackendPaymentSummary): PaymentSummary {
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
    onlineAvailable: payment.online_available,
  };
}

export function mapPayoutSettings(settings: BackendPayoutSettings): PayoutSettings {
  return {
    channel: settings.channel,
    chosen: settings.chosen,
    allowedChannels: settings.allowed_channels,
    destinationPhone: settings.destination_phone,
  };
}

export function mapSupportTicket(ticket: BackendSupportTicket): SupportTicket {
  return {
    id: ticket.id,
    category: ticket.category,
    message: ticket.message,
    interventionId: ticket.intervention_id,
    interventionTradeLabel: ticket.intervention_trade_label,
    status: ticket.status,
    adminReply: ticket.admin_reply,
    repliedAt: ticket.replied_at,
    resolvedAt: ticket.resolved_at,
    createdAt: ticket.created_at,
  };
}

export function mapAdminSupportTicket(ticket: BackendAdminSupportTicket): AdminSupportTicket {
  return {
    ...mapSupportTicket(ticket),
    authorId: ticket.author_id,
    authorName: ticket.author_name,
    authorRole: ticket.author_role,
  };
}

export function mapIntervention(intervention: BackendIntervention): Intervention {
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
    // Absent d'une ancienne réponse : jamais de bouton supposé disponible.
    canOpenDispute: intervention.can_open_dispute ?? false,
    disputeDeadline: intervention.dispute_deadline ?? null,
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

export function mapParticipant(participant: BackendParticipant): ConversationParticipant {
  return {
    userId: participant.user_id,
    role: participant.role,
    displayName: participant.display_name,
    avatarUrl: participant.avatar_url,
    artisanProfileId: participant.artisan_profile_id,
  };
}

export function mapConversationSummary(summary: BackendConversationSummary): ConversationSummary {
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

export function mapConversation(conversation: BackendConversation): ConversationDetail {
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

export function mapArtisan(
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
    // Prix indicatif réel : le tarif horaire le plus bas parmi les métiers
    // déclarés (`hourly_rate_fcfa`, exposé publiquement par ArtisanTradeOut).
    // Sans métier déclaré, une mention neutre plutôt qu'un montant inventé.
    priceBase: lowestRate != null ? `Dès ${formatFcfa(lowestRate)}/h` : 'Tarif sur devis',
    priceNumber: lowestRate ?? 0,
    tags: item.trades.map((t) => t.trade.label_fr),
    tradeCodes: item.trades.map((t) => t.trade.code),
    bio: item.bio ?? '',
    stats: {
      experience: item.years_experience != null ? `${item.years_experience} ans` : 'Non communiqué',
    },
    realisations: [],
    reviews,
    available: item.is_available,
  };
}

export function mapArtisanTradeDetail(item: BackendArtisanTrade): ArtisanTradeDetail {
  return {
    id: item.id,
    tradeCode: item.trade.code,
    tradeLabel: item.trade.label_fr,
    hourlyRateFcfa: item.hourly_rate_fcfa,
    serviceRadiusM: item.service_radius_m,
    hasCustomServiceArea: item.has_custom_service_area,
  };
}

export function mapMyArtisanProfile(item: BackendArtisanDetail): MyArtisanProfile {
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

export function mapMyReceivedReview(review: BackendMyReceivedReview): MyReceivedReview {
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

export function mapMediaUploadLimits(limits: BackendMediaUploadLimits) {
  return { maxUploadBytes: limits.max_upload_bytes, maxSidePx: limits.max_side_px };
}

export function mapProfileMediaConstraints(
  item: BackendProfileMediaConstraints,
): ProfileMediaConstraints {
  return {
    acceptedMimeTypes: item.accepted_mime_types,
    maxPixels: item.max_pixels,
    avatar: mapMediaUploadLimits(item.avatar),
    cover: mapMediaUploadLimits(item.cover),
  };
}

export function mapVerificationDocument(item: BackendVerificationDocument): VerificationDocument {
  return {
    id: item.id,
    docType: item.doc_type,
    status: item.status,
    note: item.note,
    createdAt: item.created_at,
    reviewedAt: item.reviewed_at,
  };
}

export function mapMyVerification(item: BackendMyVerification): MyVerification {
  return {
    verifiedStatus: item.verified_status,
    documents: item.documents.map(mapVerificationDocument),
  };
}

export function mapAdminVerificationListItem(
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

export function mapAdminVerificationReview(
  item: BackendAdminVerificationReview,
): AdminVerificationReview {
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

export function mapArtisanStats(stats: BackendArtisanStats): ArtisanStats {
  return {
    ratingAvg: stats.rating_avg,
    reviewCount: stats.review_count,
    interventionsCount: stats.interventions_count,
    responseRate: stats.response_rate,
    revenueFcfa: 'revenue_fcfa' in stats ? stats.revenue_fcfa : null,
  };
}

export function mapTrade(trade: BackendTrade): Trade {
  return { id: trade.id, code: trade.code, labelFr: trade.label_fr };
}
