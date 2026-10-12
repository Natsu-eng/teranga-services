import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { AdminLayout } from './AdminLayout';
import { useAuth } from '../auth/hooks/useAuth';
import type { AuthContextValue } from '../auth/auth-context';

vi.mock('../auth/hooks/useAuth');

const mockedUseAuth = vi.mocked(useAuth);

function authValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    user: null,
    role: 'admin',
    isAuthenticated: true,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="admin" element={<AdminLayout />}>
          <Route index element={<p>Contenu vue d’ensemble</p>} />
          <Route path="avis" element={<p>Contenu avis</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
});

describe('AdminLayout', () => {
  it('relie les huit sections du back-office et rend la section courante', () => {
    mockedUseAuth.mockReturnValue(authValue());

    renderAt('/admin/avis');

    const nav = screen.getByRole('navigation', { name: 'Sections admin' });
    const labels = within(nav)
      .getAllByRole('link')
      .map((link) => link.textContent);
    expect(labels).toEqual([
      'Vue d’ensemble',
      'Vérifications',
      'Artisans',
      'Utilisateurs',
      'Avis',
      'Litiges',
      'Commissions',
      'Journal',
    ]);
    expect(screen.getByText('Contenu avis')).toBeInTheDocument();
    // La section courante est signalée par aria-current, pas seulement la couleur ;
    // « Vue d’ensemble » (/admin) n'est active que sur sa propre page.
    expect(within(nav).getByRole('link', { name: 'Avis' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Vue d’ensemble' })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('se déconnecte depuis l’en-tête', () => {
    const logout = vi.fn();
    mockedUseAuth.mockReturnValue(authValue({ logout }));

    renderAt('/admin');
    fireEvent.click(screen.getByRole('button', { name: /Déconnexion/ }));

    expect(logout).toHaveBeenCalled();
  });
});
