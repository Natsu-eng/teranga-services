import type { Role } from '../../lib/api/auth-client';
import type { UserRole } from '../../types';

/**
 * The UI only ever distinguishes client/artisan (an `admin` account, if
 * ever logged in through this app, falls back to the client experience —
 * there is no admin UI here). Replaces the old self-declared `userRole`
 * toggle (audit finding): the displayed role is always derived from the
 * backend-issued role, never chosen client-side.
 */
export function toDisplayRole(role: Role | null): UserRole {
  return role === 'artisan' ? 'artisan' : 'client';
}
