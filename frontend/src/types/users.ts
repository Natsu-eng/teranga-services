/**
 * Compte connecté et rôle affiché.
 */
export type UserRole = 'client' | 'artisan';

export interface CurrentUser {
  id: string;
  name: string;
  initials: string;
  verified: boolean;
  // Real artisan_profile.id (from GET /auth/me), null for a client or an
  // artisan account without a profile yet — never a placeholder.
  artisanId: string | null;
}
