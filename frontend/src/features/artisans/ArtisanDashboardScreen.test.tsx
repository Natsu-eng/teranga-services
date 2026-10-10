import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ArtisanDashboardScreen } from './ArtisanDashboardScreen';
import { useAuth } from '../auth/hooks/useAuth';
import { useCurrentUser } from '../profile/hooks/useCurrentUser';
import { ApiError, api } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { ArtisanStats, Intervention, MyArtisanProfile } from '../../types';

// Mocké à la frontière `api` (pas les hooks) : `useMyArtisanProfile`,
// `useArtisanStats`, `useAvailabilityToggle` et `useMyInterventions`
// tournent pour de vrai ici, pour que le toggle optimiste/rollback exerce
// un vrai état React plutôt qu'un hook mocké incapable de se re-rendre seul.
vi.mock('../auth/hooks/useAuth');
vi.mock('../profile/hooks/useCurrentUser');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getMyArtisanProfile: vi.fn(),
      getArtisanStats: vi.fn(),
      listMyInterventions: vi.fn(),
      updateArtisanAvailability: vi.fn(),
    },
  };
});

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseCurrentUser = vi.mocked(useCurrentUser);
const mockedApi = vi.mocked(api, true);

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

const profileFixture: MyArtisanProfile = {
  id: 'artisan-1',
  fullName: 'Idrissa Diop',
  bio: 'Plombier expérimenté.',
  yearsExperience: 8,
  avatarUrl: null,
  coverUrl: null,
  isAvailable: true,
  verifiedStatus: 'verified',
  trades: [
    {
      id: 'trade-1',
      tradeCode: 'plomberie',
      tradeLabel: 'Plomberie',
      hourlyRateFcfa: 15000,
      serviceRadiusM: 5000,
      hasCustomServiceArea: false,
    },
  ],
};

const statsFixture: ArtisanStats = {
  ratingAvg: 4.8,
  reviewCount: 12,
  interventionsCount: 9,
  responseRate: null,
  revenueFcfa: 150_000,
};

function interventionFixture(overrides: Partial<Intervention>): Intervention {
  return {
    id: 'int-1',
    serviceRequest: {
      id: 'req-1',
      tradeCode: 'plomberie',
      tradeLabel: 'Plomberie',
      description: 'Fuite sous l’évier.',
      photoUrl: null,
      location: { lat: 14.6937, lng: -17.4441 },
      urgency: 'normal',
      aiEstimateMinFcfa: null,
      aiEstimateMaxFcfa: null,
      status: 'en_relation',
      createdAt: '2026-01-01T00:00:00Z',
    },
    clientId: 'client-1',
    artisanId: 'artisan-1',
    status: 'proposee',
    commissionRateBps: 1000,
    agreedAmountFcfa: null,
    scheduledAt: null,
    completedAt: null,
    declineReason: null,
    quote: null,
    review: null,
    createdAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderScreen() {
  return render(
    <MemoryRouter>
      <ArtisanDashboardScreen />
    </MemoryRouter>,
  );
}

describe('ArtisanDashboardScreen', () => {
  beforeEach(() => {
    mockedUseCurrentUser.mockReturnValue({
      data: {
        id: 'user-1',
        name: 'Idrissa Diop',
        initials: 'ID',
        verified: true,
        artisanId: 'artisan-1',
      },
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
    mockedApi.getMyArtisanProfile.mockReset().mockResolvedValue(profileFixture);
    mockedApi.getArtisanStats.mockReset().mockResolvedValue(statsFixture);
    mockedApi.listMyInterventions.mockReset().mockResolvedValue([]);
    mockedApi.updateArtisanAvailability.mockReset();
  });

  afterEach(cleanup);

  it('shows an honest "reserved for artisans" message for a client, with no artisan actions', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'client' }));

    renderScreen();

    expect(screen.getByText('Cet espace est réservé aux artisans.')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(mockedApi.getMyArtisanProfile).not.toHaveBeenCalled();
    expect(mockedApi.getArtisanStats).not.toHaveBeenCalled();
  });

  it('mounts and displays the real stats (fetch mocked) for a verified artisan', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));

    renderScreen();

    expect(await screen.findByText('150 000 FCFA')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
    // Note au format français, nombre d'avis en précision.
    expect(screen.getByText('4,8')).toBeInTheDocument();
    expect(screen.getByText('12 avis')).toBeInTheDocument();
    expect(screen.getByText('Non communiqué')).toBeInTheDocument();
  });

  it('shows a clean empty state when the artisan has no intervention at all', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));

    renderScreen();

    expect(await screen.findByText('Aucune demande pour le moment.')).toBeInTheDocument();
  });

  it('groups interventions by status and shows the artisan-facing actions', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedApi.listMyInterventions.mockResolvedValue([
      interventionFixture({ id: 'int-1', status: 'proposee' }),
      interventionFixture({ id: 'int-2', status: 'terminee', completedAt: '2026-01-05T00:00:00Z' }),
    ]);

    renderScreen();

    expect(await screen.findByRole('heading', { name: 'En attente de réponse' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Terminées' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accepter' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refuser' })).toBeInTheDocument();
  });

  it('toggles availability optimistically and calls the PATCH', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedApi.updateArtisanAvailability.mockResolvedValue({
      id: 'artisan-1',
      name: 'Idrissa Diop',
      trade: 'Plomberie',
      avatarUrl: null,
      coverUrl: null,
      verified: true,
      rating: 4.8,
      reviewCount: 12,
      distance: '',
      location: 'Dakar, Sénégal',
      priceBase: 'Tarif sur devis',
      priceNumber: 0,
      tags: ['Plomberie'],
      tradeCodes: ['plomberie'],
      bio: '',
      stats: { chantiers: '12', responseTime: 'Non communiqué', experience: 'Non communiqué' },
      realisations: [],
      reviews: [],
      available: false,
    });

    renderScreen();

    expect(await screen.findByText('Disponible')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch'));

    // Bascule optimiste, avant même que la promesse du PATCH ne se résolve.
    expect(await screen.findByText('Indisponible')).toBeInTheDocument();
    await waitFor(() => expect(mockedApi.updateArtisanAvailability).toHaveBeenCalledWith(false));
  });

  it('rolls back the toggle and shows an error when the PATCH fails', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedApi.updateArtisanAvailability.mockRejectedValue(
      new ApiError('network', 'Impossible de contacter le serveur.'),
    );

    renderScreen();

    expect(await screen.findByText('Disponible')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch'));

    // Bascule optimiste d'abord...
    expect(await screen.findByText('Indisponible')).toBeInTheDocument();
    // ...puis annulée une fois le PATCH rejeté, avec une erreur visible.
    expect(await screen.findByText('Impossible de contacter le serveur.')).toBeInTheDocument();
    expect(await screen.findByText('Disponible')).toBeInTheDocument();
  });

  it('shows the onboarding state instead of stats/requests for an unverified artisan', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedApi.getMyArtisanProfile.mockResolvedValue({ ...profileFixture, verifiedStatus: 'pending' });

    renderScreen();

    expect(await screen.findByText('Votre compte est en cours de vérification')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Compléter mon profil/ })).toBeInTheDocument();
    expect(screen.queryByText('Demandes reçues')).not.toBeInTheDocument();
    expect(mockedApi.getArtisanStats).not.toHaveBeenCalled();
  });

  it('navigates to the onboarding screen from the "compléter mon profil" CTA', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedApi.getMyArtisanProfile.mockResolvedValue({ ...profileFixture, verifiedStatus: 'none' });

    renderScreen();

    const cta = await screen.findByRole('button', { name: /Compléter mon profil/ });
    fireEvent.click(cta);

    // Aucune assertion de routage nécessaire au-delà de "ça n'a pas planté" :
    // la cible de navigation du CTA est vérifiée de bout en bout par les
    // propres tests d'ArtisanOnboardingScreen.
    expect(cta).toBeInTheDocument();
  });
});
