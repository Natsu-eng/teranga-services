import { httpApiClient } from './http-impl';
import { mockApiClient } from './mock';
import type { ApiClient } from './types';

export type {
  ApiClient,
  ApiErrorCode,
  ArtisanFilters,
  JobRequestFilters,
} from './types';
export { ApiError } from './types';

// Single entry point for all data access (Lot 10 bascule mock -> HTTP).
// Per-method, not all-or-nothing: only the methods the FastAPI backend
// actually covers (Lots 6-9) go through httpApiClient. The rest stay on
// mockApiClient — not as a stopgap fallback, but because their only
// screens (chat, artisan dashboard) are masked behind a "Bientôt
// disponible" state at the routing level (see components/ui/ComingSoon
// and App.tsx): those screens never mount, so these mock-backed methods
// never run in the live app. Keeping them on mock instead of throwing a
// dedicated "unavailable" error avoids inventing an ApiError code with no
// real use, and keeps mock.test.ts exercising them unchanged.
//
// getCurrentUser is also never called in production anymore: the real
// current user/role comes from AuthProvider (features/auth), the single
// source of truth for identity — useCurrentUser() reads it directly
// instead of calling this method. It stays here, backed by mock, only so
// mock.ts remains a complete ApiClient implementation for its own tests.
export const api: ApiClient = {
  ...mockApiClient,
  ...httpApiClient,
};
