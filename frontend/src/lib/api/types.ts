import type {
  Artisan,
  ArtisanStats,
  ChatMessage,
  Intervention,
  JobRequest,
  AIAnalysisResult,
  CurrentUser,
  Review,
  ServiceRequest,
  Trade,
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
}
