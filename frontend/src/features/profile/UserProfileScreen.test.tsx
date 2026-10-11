import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { UserProfileScreen } from './UserProfileScreen';
import { useAuth } from '../auth/hooks/useAuth';
import { useCurrentUser } from './hooks/useCurrentUser';
import { useMyArtisanProfile } from '../artisans/hooks/useMyArtisanProfile';
import { ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';

vi.mock('../auth/hooks/useAuth');
vi.mock('./hooks/useCurrentUser');
vi.mock('../artisans/hooks/useMyArtisanProfile');

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseCurrentUser = vi.mocked(useCurrentUser);
const mockedUseMyArtisanProfile = vi.mocked(useMyArtisanProfile);

function authValue(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    role: null,
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

function renderScreen() {
  return render(
    <MemoryRouter>
      <UserProfileScreen location="Dakar Plateau" />
    </MemoryRouter>,
  );
}

describe('UserProfileScreen', () => {
  const updateFullName = vi.fn();

  beforeEach(() => {
    updateFullName.mockReset();
    mockedUseAuth.mockReturnValue(authValue({ role: 'client', updateFullName }));
    mockedUseCurrentUser.mockReturnValue({
      data: {
        id: 'user-1',
        name: 'Diandé Diallo',
        initials: 'DD',
        verified: true,
        artisanId: null,
      },
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
  });

  afterEach(cleanup);

  it('shows the current name with no edit input visible', () => {
    renderScreen();

    expect(screen.getByText('Diandé Diallo')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Enregistrer' })).not.toBeInTheDocument();
  });

  it('opens an edit input pre-filled with the current name on clicking the pencil', () => {
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));

    expect(screen.getByDisplayValue('Diandé Diallo')).toBeInTheDocument();
  });

  it('saves the edited name and returns to display mode', async () => {
    updateFullName.mockResolvedValue(undefined);
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));
    const input = screen.getByDisplayValue('Diandé Diallo');
    fireEvent.change(input, { target: { value: 'Diandé D. Diallo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));

    await waitFor(() => expect(updateFullName).toHaveBeenCalledWith('Diandé D. Diallo'));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Enregistrer' })).not.toBeInTheDocument(),
    );
  });

  it('cancels editing without calling updateFullName', () => {
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));
    fireEvent.change(screen.getByDisplayValue('Diandé Diallo'), { target: { value: 'Autre nom' } });
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }));

    expect(updateFullName).not.toHaveBeenCalled();
    expect(screen.getByText('Diandé Diallo')).toBeInTheDocument();
  });

  it("shows the backend's error message inline when the update is rejected", async () => {
    updateFullName.mockRejectedValue(
      new ApiError('validation', 'Le nom est requis (au moins 2 caractères).'),
    );
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));
    fireEvent.change(screen.getByDisplayValue('Diandé Diallo'), { target: { value: 'A' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));

    expect(
      await screen.findByText('Le nom est requis (au moins 2 caractères).'),
    ).toBeInTheDocument();
  });

  describe('profil client', () => {
    it('est orienté vers les besoins du client (demandes, interventions, nouvelle demande)', () => {
      renderScreen();

      expect(screen.getByText('Compte client')).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /Nouvelle demande/ })).toHaveAttribute(
        'href',
        '/demande',
      );
      expect(screen.getByRole('link', { name: /Mes demandes/ })).toHaveAttribute(
        'href',
        '/mes-demandes',
      );
      expect(screen.getByRole('link', { name: /Devis et travaux/ })).toHaveAttribute(
        'href',
        '/mes-interventions',
      );
      expect(screen.queryByRole('link', { name: /Tableau de bord/ })).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /Mes gains/ })).not.toBeInTheDocument();
    });

    it('présente les moyens de paiement sans faux choix, et mène à ses paiements', () => {
      renderScreen();

      expect(screen.getByText('Moyens de paiement au Sénégal')).toBeInTheDocument();
      // Le moyen se choisit au moment de payer un devis, jamais à l'avance.
      expect(screen.queryByRole('radio')).not.toBeInTheDocument();
      expect(screen.getByText(/Téranga conserve votre argent/)).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /Mes paiements/ })).toHaveAttribute(
        'href',
        '/mes-paiements',
      );
    });
  });

  describe('profil artisan', () => {
    beforeEach(() => {
      mockedUseAuth.mockReturnValue(authValue({ role: 'artisan', updateFullName }));
      mockedUseCurrentUser.mockReturnValue({
        data: {
          id: 'user-2',
          name: 'Idrissa Diop',
          initials: 'ID',
          verified: true,
          artisanId: 'a1',
        },
        isLoading: false,
        error: null,
        reload: vi.fn(),
      });
      mockedUseMyArtisanProfile.mockReturnValue({
        data: {
          id: 'a1',
          fullName: 'Idrissa Diop',
          bio: null,
          yearsExperience: null,
          avatarUrl: null,
          coverUrl: null,
          isAvailable: true,
          verifiedStatus: 'pending',
          trades: [],
        },
        isLoading: false,
        error: null,
        reload: vi.fn(),
        setData: vi.fn(),
      });
    });

    it('est orienté vers son activité : tableau de bord, profil Pro complet, fiche publique', () => {
      renderScreen();

      expect(screen.getByRole('link', { name: /Tableau de bord/ })).toHaveAttribute('href', '/pro');
      expect(screen.getByRole('link', { name: /Mes gains et versements/ })).toHaveAttribute(
        'href',
        '/pro/gains',
      );
      expect(screen.getByRole('link', { name: /Modifier mon profil Pro/ })).toHaveAttribute(
        'href',
        '/pro/onboarding',
      );
      expect(screen.getByRole('link', { name: /Voir ma fiche publique/ })).toHaveAttribute(
        'href',
        '/artisans/a1',
      );
      expect(screen.getByText('Votre compte est en cours de vérification')).toBeInTheDocument();
    });

    it('ne montre ni parcours client ni moyens de paiement', () => {
      renderScreen();

      expect(screen.queryByText('Moyens de paiement au Sénégal')).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /Mes demandes/ })).not.toBeInTheDocument();
      expect(screen.queryByText('Compte client')).not.toBeInTheDocument();
    });
  });

  describe('compte hérité (nom resté au numéro de téléphone)', () => {
    beforeEach(() => {
      mockedUseCurrentUser.mockReturnValue({
        data: {
          id: 'user-3',
          name: '+221777278808',
          initials: '+',
          verified: true,
          artisanId: null,
        },
        isLoading: false,
        error: null,
        reload: vi.fn(),
      });
    });

    it('n’affiche pas le numéro comme un nom et invite à en saisir un', () => {
      renderScreen();

      expect(screen.getByRole('heading', { name: 'Nom à compléter' })).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: /221/ })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Ajouter mon nom' })).toBeInTheDocument();
    });

    it('ne propose jamais le numéro comme valeur de départ du nom', () => {
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: 'Ajouter mon nom' }));

      expect(screen.getByLabelText('Nom complet')).toHaveValue('');
    });
  });
});
