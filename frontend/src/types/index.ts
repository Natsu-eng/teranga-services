export type UserRole = 'client' | 'artisan';

export interface Review {
  id: string;
  author: string;
  avatarInitials: string;
  rating: number;
  date: string;
  comment: string;
  /**
   * Statut de modération, dit tel quel par le serveur : `signale` = signalé
   * par l'artisan, en attente de décision (toujours visible et compté).
   * Absent sur les données de démonstration.
   */
  moderationStatus?: 'publie' | 'masque' | 'signale';
}

/** Un avis reçu, vu par l'artisan lui-même (masqués compris). */
export interface MyReceivedReview {
  id: string;
  rating: number;
  comment: string;
  authorName: string;
  createdAt: string;
  status: 'publie' | 'masque' | 'signale';
  reportReason: string | null;
  reportedAt: string | null;
  /** Un seul signalement par avis, et seulement sur un avis publié. */
  canReport: boolean;
}

export interface Realisation {
  id: string;
  title: string;
  imageUrl: string;
  altText: string;
}

export interface Trade {
  id: string;
  code: string;
  labelFr: string;
}

export interface Artisan {
  id: string;
  name: string;
  trade: string; // e.g., 'Plomberie', 'Électricité', 'Climatisation'
  avatarUrl: string | null;
  coverUrl: string | null;
  verified: boolean;
  rating: number;
  reviewCount: number;
  distance: string;
  location: string;
  priceBase: string; // e.g. "15.000 CFA"
  priceNumber: number;
  tags: string[];
  /**
   * Codes métier déclarés (ex. « plomberie »), dans le même ordre que `tags`.
   * Nécessaires pour proposer une demande de devis : le serveur refuse de
   * mettre un client en relation avec un artisan qui n'exerce pas le métier
   * de sa demande (ArtisanMetierNonExerce).
   */
  tradeCodes: string[];
  bio: string;
  stats: {
    chantiers: string; // e.g. "150+"
    responseTime: string; // e.g. "< 1h"
    experience: string; // e.g. "8 ans"
  };
  realisations: Realisation[];
  reviews: Review[];
  available: boolean;
}

export interface AIAnalysisResult {
  trade: string;
  // Backend trade code (e.g. "plomberie") backing `trade` (its French label) —
  // the value a service_request/artisan search actually filters on, kept
  // alongside the display label instead of forcing callers to reverse-map it.
  tradeCode: string;
  priceEstimate: string;
  // Raw FCFA bounds backing `priceEstimate`'s formatted string — needed to
  // relay the AI's estimate to `POST /requests` (ai_estimate_min/max_fcfa).
  priceMinFcfa: number;
  priceMaxFcfa: number;
  recommendedCount: number;
  explanation: string;
  urgency: string;
  // Backend urgency enum backing `urgency` (its French display label).
  urgencyCode: 'normal' | 'urgent' | 'immediat';
  suggestedDevis: {
    title: string;
    labor: number;
    materials: number;
    total: number;
  };
}

export type ServiceRequestStatus = 'ouverte' | 'en_relation' | 'convertie' | 'annulee' | 'expiree';

export interface ServiceRequest {
  id: string;
  tradeCode: string;
  tradeLabel: string;
  description: string;
  photoUrl: string | null;
  location: { lat: number; lng: number };
  /** Lieu confirmé par le client (« Dakar Plateau »…) ; null pour les demandes antérieures. */
  locationLabel: string | null;
  urgency: string;
  aiEstimateMinFcfa: number | null;
  aiEstimateMaxFcfa: number | null;
  status: ServiceRequestStatus;
  /** Demande ouverte : date à laquelle elle expirera sans artisan (sinon null). */
  expiresAt: string | null;
  createdAt: string;
}

/**
 * Pourquoi un artisan ne peut pas recevoir une demande — même règle que
 * l'envoi (POST /interventions), lue AVANT d'envoyer.
 */
export type EngagementBlocker = 'artisan_non_verifie' | 'metier_non_exerce' | 'hors_zone';

export interface EngagementCheck {
  eligible: boolean;
  reason: EngagementBlocker | null;
}

export interface RequestEligibility extends EngagementCheck {
  requestId: string;
}

export type InterventionStatus =
  'proposee' | 'acceptee' | 'en_cours' | 'terminee' | 'annulee' | 'litige';

export type QuoteStatus = 'propose' | 'accepte' | 'refuse' | 'expire';

export interface Quote {
  id: string;
  laborFcfa: number;
  materialsFcfa: number;
  totalFcfa: number;
  status: QuoteStatus;
  createdAt: string;
}

/*
 * Paiements (BUILD_PLAN.md §3.5). Montants en FCFA ENTIERS, taux en points
 * de base (1 000 = 10 %) : le front n'en calcule aucun, il affiche ceux du
 * serveur.
 */
export type PaymentChannel = 'wave' | 'orange_money' | 'free_money' | 'carte' | 'cash';

/**
 * En ligne (séquestre) : en_attente -> retenu -> libere | rembourse ;
 * checkout abandonné : echoue | annule. Espèces : reussi (réglé
 * directement à l'artisan) ou annule.
 */
export type PaymentStatus =
  'en_attente' | 'retenu' | 'libere' | 'reussi' | 'echoue' | 'annule' | 'rembourse';

export type PlatformFeeStatus = 'due' | 'collectee' | 'annulee';
export type PayoutChannel = 'wave' | 'orange_money' | 'bank';
export type PayoutStatus = 'en_attente' | 'envoye' | 'echoue';

export interface PaymentSummary {
  /** Prix du devis accepté : ce que paie le client, sans frais ajoutés. */
  amountFcfa: number;
  commission: {
    rateBps: number;
    amountFcfa: number;
    /** `null` : pas encore enregistrée (estimation sur le taux figé). */
    status: PlatformFeeStatus | null;
  };
  /** Ce que touche l'artisan : montant − commission. */
  netFcfa: number;
  /** `null` : aucun paiement initié. */
  status: PaymentStatus | null;
  channel: PaymentChannel | null;
  checkoutUrl: string | null;
  checkoutExpiresAt: string | null;
  paidAt: string | null;
  releasedAt: string | null;
  refundedAt: string | null;
  payout: {
    status: PayoutStatus;
    amountFcfa: number;
    channel: PayoutChannel;
    sentAt: string | null;
  } | null;
}

export type CancellationKind = 'refus' | 'annulation' | 'arbitrage';

export interface Cancellation {
  kind: CancellationKind;
  by: UserRole | 'admin';
  reason: string | null;
  at: string;
}

export interface Dispute {
  openedBy: UserRole | 'admin';
  reason: string;
  openedAt: string;
  outcome: 'libere' | 'rembourse' | null;
  resolvedAt: string | null;
  resolutionNote: string | null;
}

export interface Intervention {
  id: string;
  serviceRequest: ServiceRequest;
  clientId: string;
  artisanId: string;
  status: InterventionStatus;
  commissionRateBps: number;
  agreedAmountFcfa: number | null;
  scheduledAt: string | null;
  completedAt: string | null;
  /** Comment une intervention `annulee` a été close (refus, annulation, arbitrage). */
  cancellation: Cancellation | null;
  quote: Quote | null;
  review: Review | null;
  /** Fil de discussion client ↔ artisan, ouvert avec l'intervention (messagerie). */
  conversationId: string | null;
  /** Volet financier, dès qu'un devis est accepté (deux parties et admin seulement). */
  payment: PaymentSummary | null;
  dispute: Dispute | null;
  createdAt: string;
}

/** Moyens de paiement réellement proposés par le serveur. */
export interface PaymentOptions {
  onlineChannels: PaymentChannel[];
  cashEnabled: boolean;
  currency: string;
}

/** Un paiement dans l'historique du client. */
export interface ClientPayment {
  id: string;
  interventionId: string;
  tradeLabel: string;
  artisanName: string;
  amountFcfa: number;
  channel: PaymentChannel;
  status: PaymentStatus;
  createdAt: string;
  paidAt: string | null;
  releasedAt: string | null;
  refundedAt: string | null;
}

export interface EarningsTotals {
  paidOutFcfa: number;
  payoutPendingFcfa: number;
  inEscrowFcfa: number;
  commissionCollectedFcfa: number;
  cashReceivedFcfa: number;
  commissionDueFcfa: number;
}

export interface EarningItem {
  interventionId: string;
  tradeLabel: string;
  clientName: string;
  interventionStatus: InterventionStatus;
  payment: PaymentSummary;
}

export interface ArtisanEarnings {
  totals: EarningsTotals;
  items: EarningItem[];
}

/** Où l'artisan reçoit ses versements : toujours le numéro vérifié du compte. */
export interface PayoutSettings {
  channel: PayoutChannel;
  chosen: boolean;
  allowedChannels: PayoutChannel[];
  destinationPhone: string;
}

/**
 * Mirrors `GET /artisans/{id}/stats` (BUILD_PLAN.md §3.2, §5 Lot 9) exactly —
 * every field is either a real reputation indicator or `null` when the
 * backend has nothing honest to report yet, never an invented number.
 */
export interface ArtisanStats {
  ratingAvg: number | null;
  reviewCount: number;
  interventionsCount: number;
  // Mirrors the backend's `response_rate` verbatim (BUILD_PLAN.md §3.2) —
  // always `null` today: no `responded_at` tracking exists yet in the
  // backend model (Lot 9) to compute a real rate. No unit/scale is assumed
  // here since the backend has never populated it.
  responseRate: number | null;
  // Only present when the caller is the artisan owner or an admin
  // (`ArtisanStatsPrivateOut`) — `null` for the public view, never 0
  // standing in for "not authorized to see this".
  revenueFcfa: number | null;
}

export type ArtisanVerifiedStatus = 'none' | 'pending' | 'verified' | 'rejected';

/**
 * Un métier déclaré par l'artisan lui-même (`POST/DELETE
 * /artisans/me/trades`) — porte l'`id` nécessaire pour le retirer,
 * contrairement aux champs `tags`/`trade` en lecture seule de `Artisan`
 * (vue publique recherche/détail).
 */
export interface ArtisanTradeDetail {
  id: string;
  tradeCode: string;
  tradeLabel: string;
  hourlyRateFcfa: number;
  serviceRadiusM: number;
  hasCustomServiceArea: boolean;
}

/**
 * Le propre profil de l'artisan, tel qu'édité pendant l'onboarding
 * (`PATCH /artisans/me`, `GET /artisans/{id}` en vue de soi-même) — plus
 * riche que `Artisan` (vue publique) : expose chaque métier déclaré avec
 * son propre id/tarif/rayon plutôt qu'un seul libellé `trade` aplati.
 */
export interface MyArtisanProfile {
  id: string;
  fullName: string;
  bio: string | null;
  yearsExperience: number | null;
  avatarUrl: string | null;
  // Photo de couverture (bandeau de la fiche publique) -- même régime
  // public que `avatarUrl`, éditée depuis l'onboarding (lot feat/profile-media).
  coverUrl: string | null;
  isAvailable: boolean;
  verifiedStatus: ArtisanVerifiedStatus;
  trades: ArtisanTradeDetail[];
  /** Suspendu par un admin : invisible en recherche, aucune nouvelle demande. */
  isSuspended: boolean;
  /** Motif de la suspension, montré à l'artisan lui-même (jamais au public). */
  suspensionReason: string | null;
}

/** Limites d'envoi d'une photo du profil, telles qu'appliquées par le serveur. */
export interface MediaUploadLimits {
  maxUploadBytes: number;
  maxSidePx: number;
}

/**
 * `GET /artisans/me/media-constraints` — seule source de vérité des
 * contraintes de photo de profil/couverture (aucun plafond en dur côté front).
 */
export interface ProfileMediaConstraints {
  acceptedMimeTypes: string[];
  maxPixels: number;
  avatar: MediaUploadLimits;
  cover: MediaUploadLimits;
}

export type VerificationDocType = 'cni' | 'selfie' | 'accreditation' | 'address_proof';
export type VerificationDocStatus = 'pending' | 'approved' | 'rejected';

export interface VerificationDocument {
  id: string;
  docType: VerificationDocType;
  status: VerificationDocStatus;
  note: string | null;
  createdAt: string;
  reviewedAt: string | null;
}

export interface MyVerification {
  verifiedStatus: ArtisanVerifiedStatus;
  documents: VerificationDocument[];
}

/** Une ligne de la file d'attente admin (`GET /admin/verifications`). */
export interface AdminVerificationListItem {
  id: string;
  artisanId: string;
  artisanFullName: string;
  docType: VerificationDocType;
  status: VerificationDocStatus;
  note: string | null;
  createdAt: string;
  reviewedAt: string | null;
}

/** Résultat d'une décision admin (`approve`/`reject`) — porte le
 * `verifiedStatus` résultant de l'artisan, recalculé côté serveur. */
export interface AdminVerificationReview {
  id: string;
  docType: VerificationDocType;
  status: VerificationDocStatus;
  note: string | null;
  reviewedBy: string;
  reviewedAt: string;
  artisanId: string;
  artisanVerifiedStatus: ArtisanVerifiedStatus;
}

export interface CurrentUser {
  id: string;
  name: string;
  initials: string;
  verified: boolean;
  // Real artisan_profile.id (from GET /auth/me), null for a client or an
  // artisan account without a profile yet — never a placeholder.
  artisanId: string | null;
}

/* ------------------------------------------------------------------ Messagerie */

/**
 * Message d'un fil, identique pour les deux participants (REST et temps
 * réel). `body` est TOUJOURS la version masquée par le serveur ;
 * `contactMasked` signale qu'un numéro ou un e-mail a été retiré, pour
 * l'avertissement de transparence.
 */
export interface ChatMessage {
  id: string;
  conversationId: string;
  /** Ordre strictement croissant attribué par le serveur (curseur `since`). */
  seq: number;
  senderId: string;
  body: string;
  contactMasked: boolean;
  /** Image jointe : jamais d'URL publique, contenu lu par un appel authentifié. */
  hasAttachment: boolean;
  attachmentContentType: string | null;
  createdAt: string;
}

export interface ConversationParticipant {
  userId: string;
  role: 'client' | 'artisan';
  /** Nom public (jamais un numéro de téléphone). */
  displayName: string;
  avatarUrl: string | null;
  /** Fiche publique de l'artisan ; `null` pour un client. */
  artisanProfileId: string | null;
}

export interface ConversationSummary {
  id: string;
  interventionId: string | null;
  interventionStatus: InterventionStatus | null;
  tradeLabel: string | null;
  otherParty: ConversationParticipant;
  lastMessage: {
    body: string;
    fromMe: boolean;
    hasAttachment: boolean;
    createdAt: string;
  } | null;
  unreadCount: number;
  lastActivityAt: string;
}

export interface ConversationDetail {
  id: string;
  interventionId: string | null;
  interventionStatus: InterventionStatus | null;
  tradeLabel: string | null;
  otherParty: ConversationParticipant;
  /** Dernier message vu par l'utilisateur courant (séparateur « nouveaux »). */
  myLastReadSeq: number;
  /** Faux si la mise en relation a été refusée : fil en lecture seule. */
  canSend: boolean;
  createdAt: string;
}

/** Page d'historique, toujours du plus ancien au plus récent. */
export interface MessageHistory {
  items: ChatMessage[];
  /** Des messages plus anciens existent (remontée dans l'historique). */
  hasMore: boolean;
}
