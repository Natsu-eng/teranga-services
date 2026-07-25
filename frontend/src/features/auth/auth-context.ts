import { createContext } from 'react';
import type { AuthUser, Role } from '../../lib/api/auth-client';

export interface AuthContextValue {
  user: AuthUser | null;
  /** Always server-derived (`user.role` in the JWT/`/auth/me` response) — never a client-side choice. `null` when signed out. */
  role: Role | null;
  isAuthenticated: boolean;
  /** True until the initial session-restore attempt (via the persisted refresh token) has settled. */
  isLoading: boolean;
  requestOtp: (phone: string) => Promise<void>;
  login: (phone: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
