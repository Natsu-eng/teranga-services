import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { MyRequestsScreen } from './MyRequestsScreen';
import { useMyRequests } from './hooks/useMyRequests';
import type { ServiceRequest } from '../../types';

vi.mock('./hooks/useMyRequests');

const mockedUseMyRequests = vi.mocked(useMyRequests);

function requestFixture(overrides: Partial<ServiceRequest>): ServiceRequest {
  return {
    id: 'req-1',
    tradeCode: 'plomberie',
    tradeLabel: 'Plomberie',
    description: 'Fuite sous l’évier.',
    photoUrl: null,
    location: { lat: 14.69, lng: -17.44 },
    locationLabel: null,
    urgency: 'normal',
    aiEstimateMinFcfa: 10_000,
    aiEstimateMaxFcfa: 20_000,
    status: 'ouverte',
    createdAt: '2026-10-01T10:00:00Z',
    ...overrides,
  };
}

function renderScreen() {
  return render(
    <MemoryRouter>
      <MyRequestsScreen />
    </MemoryRouter>,
  );
}

describe('MyRequestsScreen', () => {
  beforeEach(() => mockedUseMyRequests.mockReset());
  afterEach(cleanup);

  it('invite à décrire un problème quand il n’y a aucune demande', () => {
    mockedUseMyRequests.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText("Vous n'avez pas encore de demande.")).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Décrire mon problème' })).toHaveAttribute(
      'href',
      '/demande',
    );
  });

  it('propose de choisir un artisan du bon métier, près du lieu de la demande ouverte', () => {
    mockedUseMyRequests.mockReturnValue({
      data: [requestFixture({})],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText("En attente d'un artisan")).toBeInTheDocument();
    expect(screen.getByText(/10 000 FCFA – 20 000 FCFA/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Choisir un artisan' })).toHaveAttribute(
      'href',
      '/recherche?trade=plomberie&lat=14.69&lng=-17.44',
    );
  });

  it('renvoie vers le suivi une fois la mise en relation faite, sans reproposer de choix', () => {
    mockedUseMyRequests.mockReturnValue({
      data: [requestFixture({ status: 'en_relation' })],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.queryByRole('link', { name: 'Choisir un artisan' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voir le devis et le suivi' })).toHaveAttribute(
      'href',
      '/mes-interventions',
    );
  });

  it('affiche le lieu confirmé de chaque demande', () => {
    mockedUseMyRequests.mockReturnValue({
      data: [
        requestFixture({ id: 'r1', locationLabel: 'Ouakam, Dakar' }),
        requestFixture({ id: 'r2', locationLabel: null }),
      ],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText('Lieu : Ouakam, Dakar')).toBeInTheDocument();
    expect(screen.getByText('Lieu : position GPS enregistrée')).toBeInTheDocument();
    expect(screen.queryByText(/hors de la région de Dakar/)).not.toBeInTheDocument();
  });

  it('signale une demande localisée hors de la région de Dakar', () => {
    mockedUseMyRequests.mockReturnValue({
      data: [requestFixture({ location: { lat: 48.9097, lng: 2.3819 } })],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText(/localisée hors de la région de Dakar/)).toBeInTheDocument();
  });
});
