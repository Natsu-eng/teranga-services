/**
 * Formes JSON renvoyées par le backend FastAPI (snake_case), telles que
 * consommées par `httpApiClient`. Extraites de `http-impl.ts` sans
 * changement : seules les déclarations sont désormais exportées.
 */
import type {
  Cancellation,
  Dispute,
  PaymentChannel,
  PaymentStatus,
  PayoutChannel,
  PayoutStatus,
  PlatformFeeStatus,
  VerificationDocType,
} from '../../types';

export interface BackendTrade {
  id: string;
  code: string;
  label_fr: string;
}

export interface BackendArtisanTrade {
  id: string;
  trade: BackendTrade;
  hourly_rate_fcfa: number;
  service_radius_m: number;
  has_custom_service_area: boolean;
}

export type VerifiedStatus = 'none' | 'pending' | 'verified' | 'rejected';

export interface BackendArtisanListItem {
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

export interface BackendArtisanDetail extends BackendArtisanListItem {
  cover_url: string | null;
  is_suspended: boolean;
  // Renseigné seulement pour l'artisan lui-même et l'admin : la fiche d'un
  // suspendu n'est jamais servie au public.
  suspension_reason: string | null;
}

export interface BackendMediaUploadLimits {
  max_upload_bytes: number;
  max_side_px: number;
}

export interface BackendProfileMediaConstraints {
  accepted_mime_types: string[];
  max_pixels: number;
  avatar: BackendMediaUploadLimits;
  cover: BackendMediaUploadLimits;
}

export interface BackendVerificationDocument {
  id: string;
  doc_type: VerificationDocType;
  status: 'pending' | 'approved' | 'rejected';
  note: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface BackendMyVerification {
  verified_status: VerifiedStatus;
  documents: BackendVerificationDocument[];
}

export interface BackendAdminVerificationListItem {
  id: string;
  artisan_id: string;
  artisan_full_name: string;
  doc_type: VerificationDocType;
  status: 'pending' | 'approved' | 'rejected';
  note: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface BackendAdminVerificationReview {
  id: string;
  doc_type: VerificationDocType;
  status: 'pending' | 'approved' | 'rejected';
  note: string | null;
  reviewed_by: string;
  reviewed_at: string;
  artisan_id: string;
  artisan_verified_status: VerifiedStatus;
}

export interface BackendArtisanStatsPublic {
  rating_avg: number | null;
  review_count: number;
  interventions_count: number;
  response_rate: number | null;
}

// `GET /artisans/{id}/stats` returns this wider shape instead when the
// caller is the artisan owner or an admin (app/schemas/artisans.py
// ArtisanStatsPrivateOut) -- `revenue_fcfa` is absent entirely from the
// JSON body otherwise, never sent as `null` (BUILD_PLAN.md §5 Lot 9).
export interface BackendArtisanStatsPrivate extends BackendArtisanStatsPublic {
  revenue_fcfa: number;
}

export type BackendArtisanStats = BackendArtisanStatsPublic | BackendArtisanStatsPrivate;

export interface BackendReview {
  id: string;
  rating: number;
  comment: string;
  author_name: string;
  created_at: string;
  status: 'publie' | 'masque' | 'signale';
}

export interface BackendMyReceivedReview extends BackendReview {
  report_reason: string | null;
  reported_at: string | null;
  can_report: boolean;
}

export interface BackendPage<T> {
  items: T[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

export interface BackendSuggestedQuote {
  labor_fcfa: number;
  materials_fcfa: number;
  total_fcfa: number;
}

export interface BackendTriageResult {
  // null : aucun métier reconnu (et alors aucun montant).
  trade_code: string | null;
  price_min_fcfa: number | null;
  price_max_fcfa: number | null;
  urgency: 'normal' | 'urgent' | 'immediat';
  suggested_quote: BackendSuggestedQuote | null;
}

export interface BackendLocation {
  lat: number;
  lng: number;
}

export interface BackendServiceRequest {
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

export interface BackendQuote {
  id: string;
  labor_fcfa: number;
  materials_fcfa: number;
  total_fcfa: number;
  status: 'propose' | 'accepte' | 'refuse' | 'expire';
  created_at: string;
}

export interface BackendIntervention {
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

export interface BackendCancellation {
  kind: Cancellation['kind'];
  by: Cancellation['by'];
  reason: string | null;
  at: string;
}

export interface BackendDispute {
  opened_by: Dispute['openedBy'];
  reason: string;
  opened_at: string;
  outcome: Dispute['outcome'];
  resolved_at: string | null;
  resolution_note: string | null;
}

export interface BackendPaymentSummary {
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
  online_available: boolean;
}

export interface BackendClientPayment {
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

export interface BackendEarnings {
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

export interface BackendPayoutSettings {
  channel: PayoutChannel;
  chosen: boolean;
  allowed_channels: PayoutChannel[];
  destination_phone: string;
}

export interface BackendChatMessage {
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

export interface BackendParticipant {
  user_id: string;
  role: 'client' | 'artisan';
  display_name: string;
  avatar_url: string | null;
  artisan_profile_id: string | null;
}

export interface BackendConversationSummary {
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

export interface BackendConversation {
  id: string;
  intervention_id: string | null;
  intervention_status: BackendIntervention['status'] | null;
  trade_label: string | null;
  other_party: BackendParticipant;
  my_last_read_seq: number;
  can_send: boolean;
  created_at: string;
}
