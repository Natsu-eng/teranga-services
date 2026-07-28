import { createContext } from 'react';
import type { AuthUser, Role, SignupRole } from '../../lib/api/auth-client';

export interface AuthContextValue {
  user: AuthUser | null;
  /** Always server-derived (`user.role` in the JWT/`/auth/me` response) — never a client-side choice. `null` when signed out. */
  role: Role | null;
  isAuthenticated: boolean;
  /** True until the initial session-restore attempt (via the persisted refresh token) has settled. */
  isLoading: boolean;
  requestOtp: (phone: string) => Promise<void>;
  /** Vérifie l'OTP pour un compte déjà existant. Ne crée jamais de compte — le backend rejette un numéro inconnu (BUILD_PLAN.md §4). */
  login: (phone: string, code: string) => Promise<void>;
  /** Vérifie l'OTP et crée un nouveau compte avec le rôle choisi. Le backend rejette un numéro déjà inscrit (BUILD_PLAN.md §4). */
  signup: (phone: string, code: string, role: SignupRole) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
