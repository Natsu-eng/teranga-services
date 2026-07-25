import type {
  Artisan,
  ArtisanStats,
  ChatMessage,
  JobRequest,
  AIAnalysisResult,
  CurrentUser,
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
}
