import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ArtisanDashboardScreen } from './ArtisanDashboardScreen';
import { useAuth } from '../auth/hooks/useAuth';
import { useCurrentUser } from '../profile/hooks/useCurrentUser';
import { ApiError, api } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { Artisan, ArtisanStats, Intervention } from '../../types';

// Mocked at the `api` boundary (not the hooks): `useArtisan`, `useArtisanStats`,
// `useAvailabilityToggle` and `useMyInterventions` all run for real here, so
// the optimistic toggle/rollback exercises actual React state instead of a
// hook mock that can't re-render on its own.
vi.mock('../auth/hooks/useAuth');
vi.mock('../profile/hooks/useCurrentUser');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getArtisanById: vi.fn(),
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
    logout: vi.fn(),
    ...overrides,
  };
}

const artisanFixture: Artisan = {
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
  bio: '',
  stats: { chantiers: '12', responseTime: 'Non communiqué', experience: 'Non communiqué' },
  realisations: [],
  reviews: [],
  available: true,
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
    mockedApi.getArtisanById.mockReset().mockResolvedValue(artisanFixture);
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
    expect(mockedApi.getArtisanById).not.toHaveBeenCalled();
    expect(mockedApi.getArtisanStats).not.toHaveBeenCalled();
  });

  it('mounts and displays the real stats (fetch mocked)', async () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));

    renderScreen();

    expect(await screen.findByText('150 000 FCFA')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
    expect(screen.getByText('4.8 (12)')).toBeInTheDocument();
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
    mockedApi.updateArtisanAvailability.mockResolvedValue({ ...artisanFixture, available: false });

    renderScreen();

    expect(await screen.findByText('Disponible')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch'));

    // Optimistic flip, before the PATCH promise even resolves.
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

    // Optimistic flip first...
    expect(await screen.findByText('Indisponible')).toBeInTheDocument();
    // ...then rolled back once the PATCH rejects, with a visible error.
    expect(await screen.findByText('Impossible de contacter le serveur.')).toBeInTheDocument();
    expect(await screen.findByText('Disponible')).toBeInTheDocument();
  });
});
