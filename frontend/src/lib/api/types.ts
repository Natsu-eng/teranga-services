import type {
  AdminVerificationListItem,
  AdminVerificationReview,
  Artisan,
  ArtisanStats,
  ChatMessage,
  Intervention,
  JobRequest,
  AIAnalysisResult,
  CurrentUser,
  MyArtisanProfile,
  MyVerification,
  ProfileMediaConstraints,
  Review,
  ServiceRequest,
  Trade,
  VerificationDocStatus,
  VerificationDocType,
  VerificationDocument,
} from '../../types';

export type ApiErrorCode = 'not_found' | 'validation' | 'network' | 'unknown';

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

export interface JobRequestFilters {
  status?: JobRequest['status'];
}

export interface CreateServiceRequestInput {
  tradeCode: string;
  description: string;
  photoUrl?: string | null;
  location: { lat: number; lng: number };
  urgency: 'normal' | 'urgent' | 'immediat';
  aiEstimateMinFcfa?: number | null;
  aiEstimateMaxFcfa?: number | null;
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

export interface AdminVerificationFilters {
  /** Défaut serveur `pending` si omis (la file d'attente à traiter). */
  status?: VerificationDocStatus;
}

/**
 * Contract for all data access, independent of implementation. `src/lib/api/index.ts`
 * is the only place that picks which implementation (mock today, HTTP later) satisfies it.
 */
export interface ApiClient {
  listArtisans(filters?: ArtisanFilters): Promise<Artisan[]>;
  getArtisanById(id: string): Promise<Artisan>;
  listJobRequests(filters?: JobRequestFilters): Promise<JobRequest[]>;
  getChatMessages(conversationId: string): Promise<ChatMessage[]>;
  sendChatMessage(conversationId: string, text: string): Promise<ChatMessage>;
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
  getCurrentUser(): Promise<CurrentUser>;
  listTrades(): Promise<Trade[]>;
  createServiceRequest(input: CreateServiceRequestInput): Promise<ServiceRequest>;
  listMyServiceRequests(): Promise<ServiceRequest[]>;
  listMyInterventions(): Promise<Intervention[]>;
  getInterventionById(id: string): Promise<Intervention>;
  acceptIntervention(id: string): Promise<Intervention>;
  declineIntervention(id: string, reason?: string | null): Promise<Intervention>;
  createQuote(interventionId: string, input: CreateQuoteInput): Promise<Intervention>;
  acceptQuote(interventionId: string): Promise<Intervention>;
  refuseQuote(interventionId: string): Promise<Intervention>;
  completeIntervention(id: string): Promise<Intervention>;
  createReview(interventionId: string, input: CreateReviewInput): Promise<Review>;
  listAdminVerifications(filters?: AdminVerificationFilters): Promise<AdminVerificationListItem[]>;
  getAdminVerificationDocumentBlob(verificationId: string): Promise<Blob>;
  approveVerification(verificationId: string): Promise<AdminVerificationReview>;
  rejectVerification(verificationId: string, note: string): Promise<AdminVerificationReview>;
}
