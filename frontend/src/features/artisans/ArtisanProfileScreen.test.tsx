import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ArtisanProfileScreen } from './ArtisanProfileScreen';
import { useArtisan } from './hooks/useArtisan';
import { ApiError } from '../../lib/api';
import type { Artisan } from '../../types';

vi.mock('./hooks/useArtisan');

const mockedUseArtisan = vi.mocked(useArtisan);

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
  bio: 'Bio de test pour la fiche artisan.',
  stats: { chantiers: '10+', responseTime: '< 1h', experience: '2 ans' },
  realisations: [],
  reviews: [],
  available: true,
};

function renderAtArtisan(artisanId: string) {
  return render(
    <MemoryRouter initialEntries={[`/artisans/${artisanId}`]}>
      <Routes>
        <Route path="/artisans/:artisanId" element={<ArtisanProfileScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ArtisanProfileScreen', () => {
  beforeEach(() => {
    mockedUseArtisan.mockReset();
  });

  it('shows a loading skeleton while the artisan is being fetched', () => {
    mockedUseArtisan.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
      reload: vi.fn(),
      setData: vi.fn(),
    });

    const { container } = renderAtArtisan('test-artisan');

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
    expect(screen.queryByText(artisanFixture.name)).not.toBeInTheDocument();
  });

  it('shows an error state with a working retry button', () => {
    const reload = vi.fn();
    mockedUseArtisan.mockReturnValue({
      data: null,
      isLoading: false,
      error: new ApiError('not_found', "Cet artisan n'existe pas ou n'est plus disponible."),
      reload,
      setData: vi.fn(),
    });

    renderAtArtisan('missing');

    expect(
      screen.getByText("Cet artisan n'existe pas ou n'est plus disponible."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('renders the artisan profile on success', () => {
    mockedUseArtisan.mockReturnValue({
      data: artisanFixture,
      isLoading: false,
      error: null,
      reload: vi.fn(),
      setData: vi.fn(),
    });

    renderAtArtisan(artisanFixture.id);

    expect(screen.getByText(artisanFixture.name)).toBeInTheDocument();
    expect(screen.getByText(artisanFixture.bio)).toBeInTheDocument();
  });
});
