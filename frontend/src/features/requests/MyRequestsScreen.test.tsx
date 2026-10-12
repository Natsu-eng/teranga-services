import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { MyRequestsScreen } from './MyRequestsScreen';
import { useMyRequests } from './hooks/useMyRequests';
import type { ServiceRequest } from '../../types';
import { ApiError, api } from '../../lib/api';

vi.mock('./hooks/useMyRequests');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, api: { ...actual.api, cancelServiceRequest: vi.fn() } };
});

const mockedCancel = vi.mocked(api.cancelServiceRequest);

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
    expiresAt: null,
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

  describe('annulation', () => {
    function withRequests(requests: ServiceRequest[], reload = vi.fn()) {
      mockedUseMyRequests.mockReturnValue({
        data: requests,
        isLoading: false,
        error: null,
        reload,
      });
      return reload;
    }

    // Réinitialisé APRÈS chaque test (avant, vitest remonte le rejet simulé
    // d'un mock réinitialisé comme une erreur du test) : tests indépendants.
    afterEach(() => mockedCancel.mockReset());

    it('annule une demande ouverte après confirmation, puis recharge la liste', async () => {
      const reload = withRequests([requestFixture({ id: 'r1' })]);
      mockedCancel.mockResolvedValue(requestFixture({ id: 'r1', status: 'annulee' }));
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: 'Annuler la demande' }));
      // Rien n'est annulé avant confirmation, et l'effet est expliqué.
      expect(mockedCancel).not.toHaveBeenCalled();
      expect(screen.getByText(/ne sera plus proposée aux artisans/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: "Confirmer l'annulation" }));

      await waitFor(() => expect(mockedCancel).toHaveBeenCalledWith('r1'));
      await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    });

    it('permet de revenir sans rien annuler', () => {
      withRequests([requestFixture({ id: 'r1' })]);
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: 'Annuler la demande' }));
      fireEvent.click(screen.getByRole('button', { name: 'Garder la demande' }));

      expect(screen.getByRole('button', { name: 'Annuler la demande' })).toBeInTheDocument();
      expect(mockedCancel).not.toHaveBeenCalled();
    });

    it('affiche le refus du serveur', async () => {
      withRequests([requestFixture({ id: 'r1' })]);
      mockedCancel.mockImplementation(async () => {
        throw new ApiError('validation', 'Seule une demande encore ouverte peut être annulée.');
      });
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: 'Annuler la demande' }));
      fireEvent.click(screen.getByRole('button', { name: "Confirmer l'annulation" }));

      expect(await screen.findByRole('alert')).toHaveTextContent(/encore ouverte/);
    });

    it('propose directement d’annuler une demande localisée hors de Dakar, sans recherche vaine', () => {
      withRequests([requestFixture({ location: { lat: 48.9097, lng: 2.3819 } })]);
      renderScreen();

      expect(screen.getByRole('button', { name: 'Annuler cette demande' })).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /Choisir un artisan/ })).not.toBeInTheDocument();
    });

    it('n’offre pas l’annulation d’une demande déjà reçue par un artisan', () => {
      withRequests([requestFixture({ status: 'en_relation' })]);
      renderScreen();

      expect(screen.queryByRole('button', { name: /Annuler/ })).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Voir le devis et le suivi' })).toBeInTheDocument();
    });

    it('range les demandes annulées dans « Anciennes demandes », repliées', () => {
      withRequests([
        requestFixture({ id: 'r1', description: 'Demande active.' }),
        requestFixture({ id: 'r2', status: 'annulee', description: 'Demande annulée.' }),
      ]);
      renderScreen();

      const archive = screen.getByText('Anciennes demandes (1)').closest('details') as HTMLElement;
      expect(archive).not.toHaveAttribute('open');
      expect(within(archive).getByText('Demande annulée.')).toBeInTheDocument();
      expect(within(archive).queryByRole('button', { name: /Annuler/ })).not.toBeInTheDocument();
      expect(screen.getAllByRole('article')).toHaveLength(2);
    });

    it('sans demande active, invite à décrire un nouveau besoin', () => {
      withRequests([requestFixture({ status: 'annulee' })]);
      renderScreen();

      expect(screen.getByText("Vous n'avez aucune demande en cours.")).toBeInTheDocument();
      expect(screen.getByText('Anciennes demandes (1)')).toBeInTheDocument();
    });
  });

  it('dit quand une demande ouverte expirera, et pourquoi une demande a expiré', () => {
    mockedUseMyRequests.mockReturnValue({
      data: [
        requestFixture({ id: 'r1', expiresAt: '2026-11-11T10:00:00Z' }),
        requestFixture({ id: 'r2', status: 'expiree', expiresAt: null }),
      ],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText(/expire le 11 novembre 2026 sans artisan/)).toBeInTheDocument();
    expect(screen.getByText('Anciennes demandes (1)')).toBeInTheDocument();
    expect(screen.getByText(/Restée sans artisan trop longtemps/)).toBeInTheDocument();
  });
});
