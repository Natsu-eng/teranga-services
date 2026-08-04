import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ProtectedRoute } from './ProtectedRoute';
import { useAuth } from '../../features/auth/hooks/useAuth';
import type { AuthContextValue } from '../../features/auth/auth-context';

vi.mock('../../features/auth/hooks/useAuth');

const mockedUseAuth = vi.mocked(useAuth);

function authValue(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    role: null,
    isAuthenticated: false,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={['/secret']}>
      <Routes>
        <Route path="/connexion" element={<div>Login screen</div>} />
        <Route
          path="/secret"
          element={
            <ProtectedRoute>
              <div>Secret content</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    mockedUseAuth.mockReset();
  });

  afterEach(cleanup);

  it('shows neither the protected content nor the login screen while the session is still restoring', () => {
    mockedUseAuth.mockReturnValue(authValue({ isLoading: true }));

    renderProtected();

    expect(screen.queryByText('Secret content')).not.toBeInTheDocument();
    expect(screen.queryByText('Login screen')).not.toBeInTheDocument();
  });

  it('redirects to /connexion when not authenticated', () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: false, isLoading: false }));

    renderProtected();

    expect(screen.getByText('Login screen')).toBeInTheDocument();
    expect(screen.queryByText('Secret content')).not.toBeInTheDocument();
  });

  it('renders the protected content when authenticated', () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, isLoading: false }));

    renderProtected();

    expect(screen.getByText('Secret content')).toBeInTheDocument();
    expect(screen.queryByText('Login screen')).not.toBeInTheDocument();
  });
});
