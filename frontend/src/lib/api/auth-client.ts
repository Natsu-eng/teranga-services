/**
 * Direct calls to `/api/v1/auth/*`. Deliberately not part of `ApiClient`
 * (`types.ts`/`index.ts`): authentication is a cross-cutting concern
 * consumed by `AuthProvider` and by `http.ts`'s own refresh logic, not a
 * per-screen data resource like artisans/reviews.
 */
import { apiRequest } from './http';
import type { TokenPair } from './auth-store';

export type Role = 'client' | 'artisan' | 'admin';
// Rôles réellement choisissables à l'inscription -- `admin` n'est jamais
// attribuable via l'app (BUILD_PLAN.md §4), aucun endpoint ne l'accepte.
export type SignupRole = 'client' | 'artisan';
export type AuthIntent = 'login' | 'signup';

export interface AuthUser {
  id: string;
  phone: string;
  fullName: string;
  role: Role;
  locale: 'fr' | 'wo';
  phoneVerifiedAt: string | null;
  // Real artisan_profile.id, null for a client or an artisan without a
  // profile yet — closes the user <-> artisan_profile link (AUDIT_PHASE2.md §6).
  artisanProfileId: string | null;
}

interface BackendUser {
  id: string;
  phone: string;
  full_name: string;
  role: Role;
  locale: 'fr' | 'wo';
  phone_verified_at: string | null;
  artisan_profile_id: string | null;
}

interface BackendAuthResponse extends TokenPair {
  user: BackendUser;
}

function mapUser(user: BackendUser): AuthUser {
  return {
    id: user.id,
    phone: user.phone,
    fullName: user.full_name,
    role: user.role,
    locale: user.locale,
    phoneVerifiedAt: user.phone_verified_at,
    artisanProfileId: user.artisan_profile_id,
  };
}

export const authClient = {
  async requestOtp(phone: string): Promise<void> {
    await apiRequest<null>('/auth/request-otp', { method: 'POST', body: { phone }, skipAuth: true });
  },

  async verifyOtp(
    phone: string,
    code: string,
    intent: AuthIntent,
    role?: SignupRole,
  ): Promise<{ user: AuthUser; tokens: TokenPair }> {
    const response = await apiRequest<BackendAuthResponse>('/auth/verify-otp', {
      method: 'POST',
      body: { phone, code, intent, role },
      skipAuth: true,
    });
    return { user: mapUser(response.user), tokens: { access: response.access, refresh: response.refresh } };
  },

  async me(): Promise<AuthUser> {
    const user = await apiRequest<BackendUser>('/auth/me');
    return mapUser(user);
  },

  async logout(refresh: string): Promise<void> {
    await apiRequest<null>('/auth/logout', { method: 'POST', body: { refresh }, skipAuth: true });
  },
};
