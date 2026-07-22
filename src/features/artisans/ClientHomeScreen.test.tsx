import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ClientHomeScreen } from './ClientHomeScreen';
import { useArtisans } from './hooks/useArtisans';
import { ApiError } from '../../lib/api';
import type { Artisan } from '../../types';

vi.mock('./hooks/useArtisans');

const mockedUseArtisans = vi.mocked(useArtisans);

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
  location: 'Dakar, Sénégal',
  priceBase: '10.000 CFA',
  priceNumber: 10000,
  tags: ['Plomberie'],
  bio: 'Bio de test',
  stats: { chantiers: '10+', responseTime: '< 1h', experience: '2 ans' },
  realisations: [],
  reviews: [],
  available: true,
};

describe('ClientHomeScreen', () => {
  beforeEach(() => {
    mockedUseArtisans.mockReset();
  });

  it('shows a loading skeleton while artisans are being fetched', () => {
    mockedUseArtisans.mockReturnValue({ data: null, isLoading: true, error: null, reload: vi.fn() });

    const { container } = render(
      <ClientHomeScreen setCurrentView={vi.fn()} setSelectedArtisanId={vi.fn()} />,
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

    render(<ClientHomeScreen setCurrentView={vi.fn()} setSelectedArtisanId={vi.fn()} />);

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

    render(<ClientHomeScreen setCurrentView={vi.fn()} setSelectedArtisanId={vi.fn()} />);

    expect(screen.getByText(artisanFixture.name)).toBeInTheDocument();
  });
});
