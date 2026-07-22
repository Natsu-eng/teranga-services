import { mockApiClient } from './mock';
import type { ApiClient } from './types';

export type {
  ApiClient,
  ApiErrorCode,
  ArtisanFilters,
  JobRequestFilters,
} from './types';
export { ApiError } from './types';

// Single entry point for all data access. Today this is the mock
// implementation; Phase 2 swaps this one line for an HTTP-backed client
// talking to the FastAPI backend — nothing outside src/lib/api changes.
export const api: ApiClient = mockApiClient;
