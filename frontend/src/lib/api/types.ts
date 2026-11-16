import type {
  AdminVerificationListItem,
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  MessageHistory,
  AdminVerificationReview,
  Artisan,
  ArtisanStats,
  Intervention,
  EngagementCheck,
  RequestEligibility,
  ArtisanEarnings,
  ClientPayment,
  PaymentChannel,
  PaymentOptions,
  PaymentSummary,
  PayoutChannel,
  PayoutSettings,
  AIAnalysisResult,
  MyArtisanProfile,
  MyReceivedReview,
  MyVerification,
  ProfileMediaConstraints,
  Review,
  ServiceRequest,
  Trade,
  VerificationDocStatus,
  VerificationDocType,
  VerificationDocument,
} from '../../types';
import type { AdminBackofficeApi } from './admin-backoffice';

// `not_implemented` : fonctionnalité déclarée côté front mais pas encore
// servie par le backend -- levée explicitement (`notImplemented`,
// http-impl.ts), jamais remplacée en silence par des données fictives.
// `forbidden` : 403, ressource à laquelle le compte n'a pas accès (ex. le
// fil de discussion d'autrui) -- l'écran renvoie alors proprement ailleurs.
export type ApiErrorCode =
  'not_found' | 'forbidden' | 'validation' | 'network' | 'not_implemented' | 'unknown';

export class ApiError extends Error {
  readonly code: ApiErrorCode;

  constructor(code: ApiErrorCode, message: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
  }
}

export interface ArtisanFilters {
  /** HTTP impl: the backend's trade *code* (e.g. "plomberie"), from `listTrades()`. Mock impl: matches by label, for backward compatibility with its own tests. */
  trade?: string;
  search?: string;
  minRating?: number;
  near?: { lat: number; lng: number };
  radiusM?: number;
  available?: boolean;
  sort?: 'distance' | 'rating' | 'recent';
  page?: number;
  pageSize?: number;
}

export interface CreateServiceRequestInput {
  tradeCode: string;
  description: string;
  photoUrl?: string | null;
  location: { lat: number; lng: number };
  /** Lieu que le client a vu et confirmé avant d'envoyer. */
  locationLabel: string;
  urgency: 'normal' | 'urgent' | 'immediat';
}

/** `POST /interventions` : propose une demande ouverte du client à un artisan. */
export interface CreateInterventionInput {
  serviceRequestId: string;
  artisanId: string;
}

export interface CreateQuoteInput {
  laborFcfa: number;
  materialsFcfa: number;
}

export interface CreateReviewInput {
  rating: number;
  comment: string;
}

/** `PATCH /artisans/me` (onboarding) — tous les champs sont optionnels, seuls
 * ceux réellement fournis sont appliqués côté serveur (mise à jour partielle). */
export interface UpdateArtisanProfileInput {
  // Vit sur `user.full_name`, pas `artisan_profile` -- accepté ici en plus
  // de `PATCH /users/me` pour que l'artisan n'ait qu'un seul endpoint à
  // connaître pour éditer tout son profil (fix confidentialité du contact).
  fullName?: string;
  bio?: string | null;
  yearsExperience?: number | null;
  baseLocation?: { lat: number; lng: number };
  // URL http(s) absolue uniquement (refusée en 422 sinon, côté serveur) ;
  // `null` retire la photo.
  avatarUrl?: string | null;
  coverUrl?: string | null;
  isAvailable?: boolean;
}

export interface AddArtisanTradeInput {
  tradeCode: string;
  hourlyRateFcfa: number;
  serviceRadiusM: number;
}

/** Curseurs de l'historique d'un fil (exclusifs l'un de l'autre). */
export interface MessageCursor {
  /** Messages antérieurs à ce `seq` (remontée dans l'historique). */
  before?: number;
  /** Messages postérieurs à ce `seq` (nouveaux messages, repli polling). */
  since?: number;
  limit?: number;
}

export interface ConversationFilters {
  /** Seulement les fils avec cet artisan (profil), ex. bouton « Message » de sa fiche. */
  artisanId?: string;
}

/** Ticket à usage unique pour ouvrir la connexion temps réel. */
export interface RealtimeTicket {
  ticket: string;
  expiresIn: number;
}

/** Notifications push : `enabled` faux, aucune invitation n'est proposée. */
export interface PushConfig {
  enabled: boolean;
  /** Clé publique VAPID (`applicationServerKey`), base64url ; null si désactivées. */
  vapidPublicKey: string | null;
}

/** Abonnement d'un appareil, tel que le donne `PushSubscription.toJSON()`. */
export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export interface AdminVerificationFilters {
  /** Défaut serveur `pending` si omis (la file d'attente à traiter). */
  status?: VerificationDocStatus;
}

/**
 * Contrat de tout l'accès aux données. Implémenté EN ENTIER par
 * `httpApiClient` (http-impl.ts) : ajouter une méthode ici sans l'implémenter
 * côté HTTP est une erreur de compilation, plus jamais un repli silencieux
 * sur des données fictives. Une fonctionnalité sans backend encore doit
 * passer explicitement par `notImplemented()` (http-impl.ts).
 */
export interface ApiClient extends AdminBackofficeApi {
  listArtisans(filters?: ArtisanFilters): Promise<Artisan[]>;
  getArtisanById(id: string): Promise<Artisan>;
  analyzeProblem(description: string): Promise<AIAnalysisResult>;
  getArtisanStats(artisanId: string): Promise<ArtisanStats>;
  updateArtisanAvailability(isAvailable: boolean): Promise<Artisan>;
  getMyArtisanProfile(artisanId: string): Promise<MyArtisanProfile>;
  updateMyArtisanProfile(input: UpdateArtisanProfileInput): Promise<MyArtisanProfile>;
  uploadAvatar(file: File): Promise<MyArtisanProfile>;
  uploadCover(file: File): Promise<MyArtisanProfile>;
  getProfileMediaConstraints(): Promise<ProfileMediaConstraints>;
  addArtisanTrade(input: AddArtisanTradeInput): Promise<MyArtisanProfile>;
  removeArtisanTrade(artisanTradeId: string): Promise<MyArtisanProfile>;
  listMyVerificationDocuments(): Promise<MyVerification>;
  uploadVerificationDocument(
    docType: VerificationDocType,
    file: File,
  ): Promise<VerificationDocument>;
  listTrades(): Promise<Trade[]>;
  createServiceRequest(input: CreateServiceRequestInput): Promise<ServiceRequest>;
  listMyServiceRequests(): Promise<ServiceRequest[]>;
  /** Annule une demande encore ouverte (jamais supprimée : elle reste en historique). */
  cancelServiceRequest(requestId: string): Promise<ServiceRequest>;
  /** Pour chaque demande ouverte : cet artisan peut-il la recevoir (métier, zone) ? */
  listRequestEligibility(artisanId: string): Promise<RequestEligibility[]>;
  /** Cet artisan intervient-il pour ce métier à ce lieu ? (avant de créer la demande) */
  checkArtisanCoverage(
    artisanId: string,
    tradeCode: string,
    location: { lat: number; lng: number },
  ): Promise<EngagementCheck>;
  listMyInterventions(): Promise<Intervention[]>;
  createIntervention(input: CreateInterventionInput): Promise<Intervention>;
  getInterventionById(id: string): Promise<Intervention>;
  acceptIntervention(id: string): Promise<Intervention>;
  declineIntervention(id: string, reason?: string | null): Promise<Intervention>;
  createQuote(interventionId: string, input: CreateQuoteInput): Promise<Intervention>;
  acceptQuote(interventionId: string): Promise<Intervention>;
  refuseQuote(interventionId: string): Promise<Intervention>;
  completeIntervention(id: string): Promise<Intervention>;
  /** Annulation par une partie (règles et remboursement côté serveur). */
  cancelIntervention(id: string, reason?: string | null): Promise<Intervention>;
  /** Litige : gèle l'argent jusqu'à l'arbitrage d'un admin. */
  openDispute(id: string, reason: string): Promise<Intervention>;
  createReview(interventionId: string, input: CreateReviewInput): Promise<Review>;
  /** Avis reçus par l'artisan courant, masqués compris (statut de modération). */
  listMyReviews(): Promise<MyReceivedReview[]>;
  /** Signale un avis reçu : une fois, motif obligatoire ; il reste visible jusqu'à la décision. */
  reportReview(reviewId: string, reason: string): Promise<MyReceivedReview>;
  listAdminVerifications(filters?: AdminVerificationFilters): Promise<AdminVerificationListItem[]>;
  getAdminVerificationDocumentBlob(verificationId: string): Promise<Blob>;
  approveVerification(verificationId: string): Promise<AdminVerificationReview>;
  rejectVerification(verificationId: string, note: string): Promise<AdminVerificationReview>;
  // Messagerie (REST = source de vérité ; le temps réel ne fait que notifier).
  listConversations(filters?: ConversationFilters): Promise<ConversationSummary[]>;
  getUnreadMessageCount(): Promise<number>;
  getConversation(conversationId: string): Promise<ConversationDetail>;
  listMessages(conversationId: string, cursor?: MessageCursor): Promise<MessageHistory>;
  sendMessage(conversationId: string, body: string): Promise<ChatMessage>;
  sendImageMessage(conversationId: string, file: File, caption: string): Promise<ChatMessage>;
  markConversationRead(conversationId: string, lastReadSeq: number): Promise<ConversationDetail>;
  getMessageAttachmentBlob(conversationId: string, messageId: string): Promise<Blob>;
  createRealtimeTicket(): Promise<RealtimeTicket>;
  // Notifications push (nouveau message, même application fermée).
  getPushConfig(): Promise<PushConfig>;
  /** Enregistre (ou rafraîchit) l'abonnement de cet appareil ; idempotent. */
  savePushSubscription(subscription: PushSubscriptionPayload): Promise<void>;
  /** Oublie l'abonnement de cet appareil (déconnexion). */
  deletePushSubscription(endpoint: string): Promise<void>;
  // Paiements (montant TOUJOURS fixé par le serveur, jamais envoyé).
  getPaymentOptions(): Promise<PaymentOptions>;
  initPayment(interventionId: string, channel: PaymentChannel): Promise<PaymentSummary>;
  listMyPayments(): Promise<ClientPayment[]>;
  getMyEarnings(): Promise<ArtisanEarnings>;
  getPayoutSettings(): Promise<PayoutSettings>;
  updatePayoutSettings(channel: PayoutChannel): Promise<PayoutSettings>;
  listAdminDisputes(filters?: { resolved?: boolean }): Promise<Intervention[]>;
  resolveDispute(
    interventionId: string,
    outcome: 'libere' | 'rembourse',
    note: string,
  ): Promise<Intervention>;
}
