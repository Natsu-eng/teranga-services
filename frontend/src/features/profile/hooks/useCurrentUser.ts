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
        // No user -> artisan_profile link exposed by the backend yet — a
        // placeholder, harmless because the screens that would use it
        // (chat, artisan dashboard) are masked behind "Bientôt disponible".
        artisanId: user.id,
      }
    : null;

  return { data, isLoading, error: null as ApiError | null, reload: () => undefined };
}
