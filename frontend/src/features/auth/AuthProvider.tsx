import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { authClient, type AuthUser, type SignupRole } from '../../lib/api/auth-client';
import { authStore, type TokenPair } from '../../lib/api/auth-store';
import { AuthContext, type AuthContextValue } from './auth-context';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Silent session restore on mount: the access token never survives a
  // reload (in-memory only, see auth-store.ts), but if a refresh token is
  // persisted, GET /auth/me will 401 once and http.ts's own refresh dance
  // transparently exchanges it for a fresh access token before retrying.
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      if (!authStore.getRefreshToken()) {
        setIsLoading(false);
        return;
      }
      try {
        const restoredUser = await authClient.me();
        if (!cancelled) setUser(restoredUser);
      } catch {
        if (!cancelled) authStore.clear();
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  // Registered with the (non-React) http client: fires when a refresh
  // attempt fails on a 401, so the UI reacts to a session that just died
  // server-side (revoked family, expired refresh) without a page reload.
  useEffect(() => {
    const handleForcedLogout = () => setUser(null);
    authStore.onForcedLogout(handleForcedLogout);
    return () => authStore.onForcedLogout(null);
  }, []);

  const requestOtp = useCallback((phone: string) => authClient.requestOtp(phone), []);

  const applySession = useCallback((sessionUser: AuthUser, tokens: TokenPair) => {
    authStore.setTokens(tokens);
    setUser(sessionUser);
  }, []);

  const login = useCallback(
    async (phone: string, code: string) => {
      const { user: loggedInUser, tokens } = await authClient.verifyOtp(phone, code, 'login');
      applySession(loggedInUser, tokens);
    },
    [applySession],
  );

  const signup = useCallback(
    async (phone: string, code: string, role: SignupRole, fullName: string) => {
      const { user: newUser, tokens } = await authClient.verifyOtp(
        phone,
        code,
        'signup',
        role,
        fullName,
      );
      applySession(newUser, tokens);
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    const refresh = authStore.getRefreshToken();
    authStore.clear();
    setUser(null);
    if (refresh) {
      // Best-effort revoke: the local session is already gone from the
      // user's point of view regardless of whether this network call succeeds.
      await authClient.logout(refresh).catch(() => undefined);
    }
  }, []);

  const updateFullName = useCallback(async (fullName: string) => {
    const updatedUser = await authClient.updateFullName(fullName);
    setUser(updatedUser);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      role: user?.role ?? null,
      isAuthenticated: user !== null,
      isLoading,
      requestOtp,
      login,
      signup,
      logout,
      updateFullName,
    }),
    [user, isLoading, requestOtp, login, signup, logout, updateFullName],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
