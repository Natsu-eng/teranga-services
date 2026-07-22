import type {
  Artisan,
  ArtisanStats,
  ChatMessage,
  JobRequest,
  AIAnalysisResult,
  CurrentUser,
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
  trade?: string;
  search?: string;
  minRating?: number;
}

export interface JobRequestFilters {
  status?: JobRequest['status'];
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
}
