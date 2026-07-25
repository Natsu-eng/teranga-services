import type { ApiError } from '../../../lib/api';
import type { CurrentUser } from '../../../types';
import { useAuth } from '../../auth/hooks/useAuth';

function initialsFrom(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

/**
 * The current user/role now comes from `AuthProvider` — the single source
 * of truth for identity since Lot 10 — not from an `api.getCurrentUser()`
 * call. This keeps the hook's shape (`{data, isLoading, error, reload}`)
 * so existing call sites (Header, BottomNav, UserProfileScreen) don't need
 * to change, while removing the redundant network round-trip: the auth
 * context already holds the backend user.
 */
export function useCurrentUser() {
  const { user, isLoading } = useAuth();

  const data: CurrentUser | null = user
    ? {
        id: user.id,
        name: user.fullName,
        initials: initialsFrom(user.fullName),
        verified: user.phoneVerifiedAt != null,
        // Real artisan_profile.id from GET /auth/me (Lot 12) — null for a
        // client, closing the placeholder this used to be (`= user.id`,
        // AUDIT_PHASE2.md §6).
        artisanId: user.artisanProfileId,
      }
    : null;

  return { data, isLoading, error: null as ApiError | null, reload: () => undefined };
}
