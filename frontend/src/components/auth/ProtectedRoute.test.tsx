import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ProtectedRoute } from './ProtectedRoute';
import { useAuth } from '../../features/auth/hooks/useAuth';
import type { AuthContextValue } from '../../features/auth/auth-context';
import type { SignupRole } from '../../lib/api/auth-client';

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
    updateFullName: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

function renderProtected(roles?: readonly SignupRole[]) {
  return render(
    <MemoryRouter initialEntries={['/secret']}>
      <Routes>
        <Route path="/connexion" element={<div>Login screen</div>} />
        <Route
          path="/secret"
          element={
            <ProtectedRoute roles={roles}>
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

  describe('contrôle du rôle', () => {
    it("refuse proprement un client sur un espace réservé aux artisans, sans afficher l'écran", () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));

      renderProtected(['artisan']);

      expect(
        screen.getByRole('heading', { name: 'Cet espace est réservé aux artisans.' }),
      ).toBeInTheDocument();
      expect(screen.queryByText('Secret content')).not.toBeInTheDocument();
      // Sortie proposée : l'accueil du client, pas une impasse.
      expect(screen.getByRole('link', { name: "Retour à l'accueil" })).toHaveAttribute(
        'href',
        '/accueil',
      );
    });

    it('refuse un artisan sur un espace réservé aux clients et le renvoie vers son tableau de bord', () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'artisan' }));

      renderProtected(['client']);

      expect(
        screen.getByRole('heading', { name: 'Cet espace est réservé aux clients.' }),
      ).toBeInTheDocument();
      expect(screen.queryByText('Secret content')).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Aller à mon tableau de bord' })).toHaveAttribute(
        'href',
        '/pro',
      );
    });

    it("refuse un admin sur l'espace Pro sans jamais lui proposer de lien vers l'espace admin", () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'admin' }));

      renderProtected(['artisan']);

      expect(screen.queryByText('Secret content')).not.toBeInTheDocument();
      const links = screen.getAllByRole('link');
      expect(links.every((link) => !link.getAttribute('href')?.startsWith('/admin'))).toBe(true);
    });

    it('laisse passer un rôle autorisé', () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'artisan' }));

      renderProtected(['artisan']);

      expect(screen.getByText('Secret content')).toBeInTheDocument();
    });

    it('accepte chacun des rôles listés', () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));

      renderProtected(['client', 'artisan']);

      expect(screen.getByText('Secret content')).toBeInTheDocument();
    });

    it("redirige toujours vers /connexion un visiteur non connecté, avant même d'évaluer le rôle", () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: false }));

      renderProtected(['artisan']);

      expect(screen.getByText('Login screen')).toBeInTheDocument();
      expect(screen.queryByText(/réservé/)).not.toBeInTheDocument();
    });
  });
});
