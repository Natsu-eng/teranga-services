import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { RequireAdminRoute } from './RequireAdminRoute';
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

function renderGuarded() {
  return render(
    <MemoryRouter>
      <RequireAdminRoute>
        <div>Admin content</div>
      </RequireAdminRoute>
    </MemoryRouter>,
  );
}

describe('RequireAdminRoute', () => {
  beforeEach(() => {
    mockedUseAuth.mockReset();
  });

  afterEach(cleanup);

  it('shows neither the admin content nor a 404 while the session is still restoring', () => {
    mockedUseAuth.mockReturnValue(authValue({ isLoading: true }));

    renderGuarded();

    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
    expect(screen.queryByText('Page introuvable')).not.toBeInTheDocument();
  });

  it('shows the exact same "page not found" screen as an unknown route for an unauthenticated visitor', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: null, isAuthenticated: false }));

    renderGuarded();

    expect(screen.getByText('Page introuvable')).toBeInTheDocument();
    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
  });

  it('shows the same "page not found" screen for a client -- never a distinct "access denied" message', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'client', isAuthenticated: true }));

    renderGuarded();

    expect(screen.getByText('Page introuvable')).toBeInTheDocument();
    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
  });

  it('shows the same "page not found" screen for an artisan too', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan', isAuthenticated: true }));

    renderGuarded();

    expect(screen.getByText('Page introuvable')).toBeInTheDocument();
    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
  });

  it('renders the admin content for an admin account', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'admin', isAuthenticated: true }));

    renderGuarded();

    expect(screen.getByText('Admin content')).toBeInTheDocument();
    expect(screen.queryByText('Page introuvable')).not.toBeInTheDocument();
  });
});
