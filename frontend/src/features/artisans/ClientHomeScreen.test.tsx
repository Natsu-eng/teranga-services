import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ClientHomeScreen } from './ClientHomeScreen';
import { useArtisans } from './hooks/useArtisans';
import { useTrades } from './hooks/useTrades';
import { ApiError } from '../../lib/api';
import type { Artisan } from '../../types';

vi.mock('./hooks/useArtisans');
vi.mock('./hooks/useTrades');

afterEach(cleanup);

const mockedUseArtisans = vi.mocked(useArtisans);
const mockedUseTrades = vi.mocked(useTrades);

const artisanFixture: Artisan = {
  id: 'test-artisan',
  name: 'Aissatou Sow',
  trade: 'Plomberie',
  avatarUrl: '/images/test-avatar.jpg',
  coverUrl: '/images/test-cover.jpg',
  verified: true,
  rating: 4.7,
  reviewCount: 10,
  distance: '1 km',
  priceBase: '10.000 CFA',
  priceNumber: 10000,
  tags: ['Plomberie'],
  tradeCodes: ['plomberie'],
  bio: 'Bio de test',
  stats: { experience: '2 ans' },
  realisations: [],
  reviews: [],
  available: true,
};

describe('ClientHomeScreen', () => {
  beforeEach(() => {
    mockedUseArtisans.mockReset();
    mockedUseTrades.mockReturnValue({ data: [], isLoading: false, error: null, reload: vi.fn() });
  });

  it('shows a loading skeleton while artisans are being fetched', () => {
    mockedUseArtisans.mockReturnValue({ data: null, isLoading: true, error: null, reload: vi.fn() });

    const { container } = render(
      <MemoryRouter>
        <ClientHomeScreen />
      </MemoryRouter>,
    );

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
    expect(screen.queryByText(artisanFixture.name)).not.toBeInTheDocument();
  });

  it('shows an error state with a working retry button', () => {
    const reload = vi.fn();
    mockedUseArtisans.mockReturnValue({
      data: null,
      isLoading: false,
      error: new ApiError('network', 'Impossible de charger les artisans.'),
      reload,
    });

    render(
      <MemoryRouter>
        <ClientHomeScreen />
      </MemoryRouter>,
    );

    expect(screen.getByText('Impossible de charger les artisans.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('renders the fetched artisans on success', () => {
    mockedUseArtisans.mockReturnValue({
      data: [artisanFixture],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    render(
      <MemoryRouter>
        <ClientHomeScreen />
      </MemoryRouter>,
    );

    expect(screen.getByText(artisanFixture.name)).toBeInTheDocument();
  });
});
