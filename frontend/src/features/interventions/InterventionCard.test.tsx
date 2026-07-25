import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { InterventionCard } from './InterventionCard';
import { api } from '../../lib/api';
import type { Intervention, ServiceRequest } from '../../types';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      acceptIntervention: vi.fn(),
      declineIntervention: vi.fn(),
      createQuote: vi.fn(),
      acceptQuote: vi.fn(),
      refuseQuote: vi.fn(),
      completeIntervention: vi.fn(),
      createReview: vi.fn(),
    },
  };
});

const mockedApi = vi.mocked(api, true);

const serviceRequestFixture: ServiceRequest = {
  id: 'req-1',
  tradeCode: 'electricite',
  tradeLabel: 'Électricité',
  description: 'Une prise ne fonctionne plus.',
  photoUrl: null,
  location: { lat: 14.6937, lng: -17.4441 },
  urgency: 'urgent',
  aiEstimateMinFcfa: 12_000,
  aiEstimateMaxFcfa: 25_000,
  status: 'en_relation',
  createdAt: '2026-01-01T00:00:00Z',
};

function interventionFixture(overrides: Partial<Intervention>): Intervention {
  return {
    id: 'int-1',
    serviceRequest: serviceRequestFixture,
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

describe('InterventionCard', () => {
  const onChanged = vi.fn();

  beforeEach(() => {
    onChanged.mockReset();
    mockedApi.acceptIntervention.mockReset().mockResolvedValue(interventionFixture({}));
    mockedApi.declineIntervention.mockReset().mockResolvedValue(interventionFixture({}));
    mockedApi.createQuote.mockReset().mockResolvedValue(interventionFixture({}));
    mockedApi.acceptQuote.mockReset().mockResolvedValue(interventionFixture({}));
    mockedApi.refuseQuote.mockReset().mockResolvedValue(interventionFixture({}));
    mockedApi.completeIntervention.mockReset().mockResolvedValue(interventionFixture({}));
    mockedApi.createReview.mockReset().mockResolvedValue({
      id: 'rev-1',
      author: 'Client Test',
      avatarInitials: 'CT',
      rating: 5,
      date: 'Aujourd’hui',
      comment: 'Bravo',
    });
  });

  afterEach(cleanup);

  describe('artisan flow', () => {
    it('accepts a proposed intervention', async () => {
      render(
        <InterventionCard
          intervention={interventionFixture({ status: 'proposee' })}
          role="artisan"
          onChanged={onChanged}
        />,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Accepter' }));

      await waitFor(() => expect(mockedApi.acceptIntervention).toHaveBeenCalledWith('int-1'));
      await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    });

    it('declines with an optional reason', async () => {
      render(
        <InterventionCard
          intervention={interventionFixture({ status: 'proposee' })}
          role="artisan"
          onChanged={onChanged}
        />,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Refuser' }));
      fireEvent.change(screen.getByPlaceholderText('Motif du refus (optionnel)'), {
        target: { value: 'Trop loin de chez moi.' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Confirmer le refus' }));

      await waitFor(() =>
        expect(mockedApi.declineIntervention).toHaveBeenCalledWith(
          'int-1',
          'Trop loin de chez moi.',
        ),
      );
    });

    it('submits a quote with a server-computed total, on an accepted intervention', async () => {
      render(
        <InterventionCard
          intervention={interventionFixture({ status: 'acceptee' })}
          role="artisan"
          onChanged={onChanged}
        />,
      );

      fireEvent.change(screen.getByPlaceholderText("Main d'œuvre (FCFA)"), {
        target: { value: '15000' },
      });
      fireEvent.change(screen.getByPlaceholderText('Matériaux (FCFA)'), {
        target: { value: '5000' },
      });
      expect(screen.getByText(/Total : 20 000 FCFA/)).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Envoyer le devis' }));

      await waitFor(() =>
        expect(mockedApi.createQuote).toHaveBeenCalledWith('int-1', {
          laborFcfa: 15000,
          materialsFcfa: 5000,
        }),
      );
    });

    it('shows a waiting message once a quote has been sent', () => {
      render(
        <InterventionCard
          intervention={interventionFixture({
            status: 'acceptee',
            quote: {
              id: 'q1',
              laborFcfa: 15_000,
              materialsFcfa: 5_000,
              totalFcfa: 20_000,
              status: 'propose',
              createdAt: '2026-01-02T00:00:00Z',
            },
          })}
          role="artisan"
          onChanged={onChanged}
        />,
      );

      expect(screen.getByText(/en attente de la réponse du client/)).toBeInTheDocument();
    });
  });

  describe('client flow', () => {
    it('accepts a pending quote', async () => {
      render(
        <InterventionCard
          intervention={interventionFixture({
            status: 'acceptee',
            quote: {
              id: 'q1',
              laborFcfa: 15_000,
              materialsFcfa: 5_000,
              totalFcfa: 20_000,
              status: 'propose',
              createdAt: '2026-01-02T00:00:00Z',
            },
          })}
          role="client"
          onChanged={onChanged}
        />,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Accepter le devis' }));

      await waitFor(() => expect(mockedApi.acceptQuote).toHaveBeenCalledWith('int-1'));
    });

    it('confirms completion of an in-progress intervention', async () => {
      render(
        <InterventionCard
          intervention={interventionFixture({ status: 'en_cours', agreedAmountFcfa: 20_000 })}
          role="client"
          onChanged={onChanged}
        />,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Confirmer la fin des travaux' }));

      await waitFor(() => expect(mockedApi.completeIntervention).toHaveBeenCalledWith('int-1'));
    });

    it('the review form only appears once the intervention is terminee, and posts rating + comment', async () => {
      const { rerender } = render(
        <InterventionCard
          intervention={interventionFixture({ status: 'en_cours' })}
          role="client"
          onChanged={onChanged}
        />,
      );
      expect(screen.queryByPlaceholderText(/Votre avis/)).not.toBeInTheDocument();

      rerender(
        <InterventionCard
          intervention={interventionFixture({ status: 'terminee' })}
          role="client"
          onChanged={onChanged}
        />,
      );

      fireEvent.click(screen.getByLabelText('5 étoiles'));
      fireEvent.change(screen.getByPlaceholderText(/Votre avis/), {
        target: { value: 'Très bon travail.' },
      });
      fireEvent.click(screen.getByRole('button', { name: "Publier l'avis" }));

      await waitFor(() =>
        expect(mockedApi.createReview).toHaveBeenCalledWith('int-1', {
          rating: 5,
          comment: 'Très bon travail.',
        }),
      );
    });

    it('shows the existing review instead of the form once one has been posted', () => {
      render(
        <InterventionCard
          intervention={interventionFixture({
            status: 'terminee',
            review: {
              id: 'rev-1',
              author: 'Moi',
              avatarInitials: 'M',
              rating: 4,
              date: 'Hier',
              comment: 'Bon travail.',
            },
          })}
          role="client"
          onChanged={onChanged}
        />,
      );

      expect(screen.getByText('Bon travail.')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: "Publier l'avis" })).not.toBeInTheDocument();
    });
  });
});
