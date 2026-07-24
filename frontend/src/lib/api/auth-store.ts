/**
 * Token storage, shared by the plain-fetch HTTP client (`http.ts`) and the
 * React `AuthProvider`. Deliberately not React state: `http.ts` has no
 * component tree to read a context from.
 *
 * Storage choice (Lot 10, see BUILD_PLAN.md §4) : the access token (15 min
 * TTL) lives in memory only, never persisted — it disappears on reload, but
 * `AuthProvider` re-derives it from the refresh token on mount. The refresh
 * token (30 days) is persisted in `localStorage`, a deliberate trade-off for
 * a SPA without a backend-for-frontend (no httpOnly cookie is available):
 * an XSS reading `localStorage` can exfiltrate it, but the backend already
 * defends this exact scenario (single-use rotation + whole-family
 * revocation on replay of an already-used token, `app/services/auth.py`).
 * The alternative (refresh token in memory only) would force a fresh OTP
 * login on every page reload, which is not an acceptable trade-off for a
 * mobile web app.
 */

const REFRESH_TOKEN_STORAGE_KEY = 'teranga.auth.refreshToken';

export interface TokenPair {
  access: string;
  refresh: string;
}

type ForcedLogoutListener = () => void;

let accessToken: string | null = null;
let forcedLogoutListener: ForcedLogoutListener | null = null;

function readRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
  } catch {
    // Storage unavailable (privacy mode, disabled storage) — treat as logged out.
    return null;
  }
}

function writeRefreshToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Ignore: nothing actionable if storage is unavailable.
  }
}

export const authStore = {
  getAccessToken(): string | null {
    return accessToken;
  },

  getRefreshToken(): string | null {
    return readRefreshToken();
  },

  setTokens(tokens: TokenPair): void {
    accessToken = tokens.access;
    writeRefreshToken(tokens.refresh);
  },

  clear(): void {
    accessToken = null;
    writeRefreshToken(null);
  },

  /** Registered by AuthProvider to react to a failed silent refresh (e.g. redirect to /connexion). */
  onForcedLogout(listener: ForcedLogoutListener | null): void {
    forcedLogoutListener = listener;
  },

  notifyForcedLogout(): void {
    forcedLogoutListener?.();
  },
};
