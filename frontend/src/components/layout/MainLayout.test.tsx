import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { MainLayout } from './MainLayout';
import { useAuth } from '../../features/auth/hooks/useAuth';
import type { AuthContextValue } from '../../features/auth/auth-context';
import type { AuthUser } from '../../lib/api/auth-client';
import {
  DEFAULT_REALTIME,
  RealtimeContext,
} from '../../features/messages/realtime/realtime-context';

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

function userFixture(role: AuthUser['role'], fullName: string): AuthUser {
  return {
    id: 'u1',
    phone: '+221771234501',
    fullName,
    role,
    locale: 'fr',
    phoneVerifiedAt: '2026-01-01T00:00:00Z',
    artisanProfileId: role === 'artisan' ? 'a1' : null,
  };
}

function renderLayout(path = '/accueil', setLocation = vi.fn(), unreadCount: number | null = null) {
  return render(
    <RealtimeContext.Provider value={{ ...DEFAULT_REALTIME, unreadCount }}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<MainLayout location="Dakar Plateau" setLocation={setLocation} />}>
            <Route path="/accueil" element={<p>Contenu accueil</p>} />
            <Route path="/pro" element={<p>Contenu pro</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </RealtimeContext.Provider>,
  );
}

describe('MainLayout — espace client', () => {
  beforeEach(() => mockedUseAuth.mockReset());
  afterEach(cleanup);

  it('affiche l’en-tête clair et la navigation client à 4 entrées', () => {
    mockedUseAuth.mockReturnValue(authValue({}));

    renderLayout();

    const nav = screen.getByRole('navigation', { name: 'Navigation principale' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'Accueil',
      'Recherche',
      'Messages',
      'Profil',
    ]);
    expect(within(nav).getByRole('link', { name: 'Accueil' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('banner')).not.toHaveAttribute('data-tone');
  });

  it('invite un visiteur à se connecter', () => {
    mockedUseAuth.mockReturnValue(authValue({}));

    renderLayout();

    expect(screen.getByText('Bonjour')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Se connecter' })).toHaveAttribute(
      'href',
      '/connexion',
    );
  });

  it('salue un client connecté par son prénom et donne accès à son profil', () => {
    mockedUseAuth.mockReturnValue(
      authValue({
        isAuthenticated: true,
        role: 'client',
        user: userFixture('client', 'Awa Diop'),
      }),
    );

    renderLayout();

    expect(screen.getByText('Bonjour, Awa')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Mon profil' })).toHaveAttribute('href', '/profil');
    expect(screen.queryByRole('link', { name: 'Se connecter' })).not.toBeInTheDocument();
  });

  it('n’affiche jamais un numéro de téléphone en guise de prénom (compte hérité)', () => {
    mockedUseAuth.mockReturnValue(
      authValue({
        isAuthenticated: true,
        role: 'client',
        user: userFixture('client', '+221777278808'),
      }),
    );

    renderLayout();

    expect(screen.getByText('Bonjour')).toBeInTheDocument();
    expect(screen.queryByText(/\+221/)).not.toBeInTheDocument();
  });

  it('propose un lien d’évitement vers le contenu', () => {
    mockedUseAuth.mockReturnValue(authValue({}));

    renderLayout();

    expect(screen.getByRole('link', { name: 'Aller au contenu' })).toHaveAttribute(
      'href',
      '#contenu',
    );
  });
});

describe('MainLayout — espace Pro', () => {
  beforeEach(() => mockedUseAuth.mockReset());
  afterEach(cleanup);

  it('affiche le bandeau vert profond et la navigation Pro à 3 entrées', () => {
    mockedUseAuth.mockReturnValue(
      authValue({
        isAuthenticated: true,
        role: 'artisan',
        user: userFixture('artisan', 'Idrissa Diop'),
      }),
    );

    renderLayout('/pro');

    const header = screen.getByRole('banner');
    expect(header).toHaveAttribute('data-tone', 'dark');
    expect(within(header).getByText('Pro')).toBeInTheDocument();

    const nav = screen.getByRole('navigation', { name: "Navigation de l'espace Pro" });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Tableau de bord', 'Messages', 'Profil']);
    expect(within(nav).getByRole('link', { name: 'Tableau de bord' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    // Jamais la navigation client dans l'espace Pro.
    expect(
      screen.queryByRole('navigation', { name: 'Navigation principale' }),
    ).not.toBeInTheDocument();
  });
});

describe('Sélecteur de quartier', () => {
  beforeEach(() => mockedUseAuth.mockReturnValue(authValue({})));
  afterEach(cleanup);

  it('s’ouvre, se ferme avec Échap et rend le focus au déclencheur', () => {
    renderLayout();

    const trigger = screen.getByRole('button', { name: /Dakar Plateau/ });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Dakar Plateau' })).toHaveAttribute(
      'aria-current',
      'true',
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveFocus();
  });

  it('remonte le quartier choisi', () => {
    const setLocation = vi.fn();
    renderLayout('/accueil', setLocation);

    fireEvent.click(screen.getByRole('button', { name: /Dakar Plateau/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Ouakam, Dakar' }));

    expect(setLocation).toHaveBeenCalledWith('Ouakam, Dakar');
  });
});

describe('Badge de messages non lus', () => {
  afterEach(cleanup);

  it('affiche le nombre de non-lus sur « Messages » (client), annoncé aux lecteurs d’écran', () => {
    mockedUseAuth.mockReturnValue(
      authValue({ isAuthenticated: true, role: 'client', user: userFixture('client', 'Awa Diop') }),
    );

    renderLayout('/accueil', vi.fn(), 3);

    const nav = screen.getByRole('navigation', { name: 'Navigation principale' });
    expect(within(nav).getByRole('link', { name: /Messages, 3 non lus/ })).toBeInTheDocument();
  });

  it("l'affiche aussi dans la navigation de l'espace Pro", () => {
    mockedUseAuth.mockReturnValue(
      authValue({
        isAuthenticated: true,
        role: 'artisan',
        user: userFixture('artisan', 'Idrissa Diop'),
      }),
    );

    renderLayout('/pro', vi.fn(), 1);

    const nav = screen.getByRole('navigation', { name: "Navigation de l'espace Pro" });
    expect(within(nav).getByRole('link', { name: /Messages, 1 non lu$/ })).toBeInTheDocument();
  });

  it('ne montre aucune pastille sans message non lu', () => {
    mockedUseAuth.mockReturnValue(
      authValue({ isAuthenticated: true, role: 'client', user: userFixture('client', 'Awa Diop') }),
    );

    renderLayout('/accueil', vi.fn(), 0);

    const nav = screen.getByRole('navigation', { name: 'Navigation principale' });
    expect(within(nav).getByRole('link', { name: 'Messages' })).toBeInTheDocument();
  });
});
