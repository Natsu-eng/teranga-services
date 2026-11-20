import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { InterventionCard } from './InterventionCard';
import { api } from '../../lib/api';
import type { Intervention, ServiceRequest } from '../../types';
import { paymentFixture } from '../payments/paymentFixtures';

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
      cancelIntervention: vi.fn(),
      openDispute: vi.fn(),
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
  locationLabel: null,
  urgency: 'urgent',
  status: 'en_relation',
  expiresAt: null,
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
    cancellation: null,
    payment: null,
    canOpenDispute: false,
    disputeDeadline: null,
    dispute: null,
    quote: null,
    review: null,
    conversationId: null,
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
        // Routeur requis : une intervention terminée offre le lien « Contacter l'aide ».
        { wrapper: MemoryRouter },
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
        { wrapper: MemoryRouter },
      );

      expect(screen.getByText('Bon travail.')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: "Publier l'avis" })).not.toBeInTheDocument();
    });
  });

  describe('discussion', () => {
    it('donne accès au fil rattaché, avec un libellé propre à chaque partie', () => {
      const { unmount } = render(
        <MemoryRouter>
          <InterventionCard
            intervention={interventionFixture({ conversationId: 'fil-1' })}
            role="client"
            onChanged={vi.fn()}
          />
        </MemoryRouter>,
      );
      expect(screen.getByRole('link', { name: "Discuter avec l'artisan" })).toHaveAttribute(
        'href',
        '/messages/fil-1',
      );
      unmount();

      render(
        <MemoryRouter>
          <InterventionCard
            intervention={interventionFixture({ conversationId: 'fil-1' })}
            role="artisan"
            onChanged={vi.fn()}
          />
        </MemoryRouter>,
      );
      expect(screen.getByRole('link', { name: 'Discuter avec le client' })).toHaveAttribute(
        'href',
        '/messages/fil-1',
      );
    });
  });

  describe('paiement, annulation et litige', () => {
    // En cours : le serveur autorise le signalement (`can_open_dispute`).
    const inProgress = (payment = paymentFixture()) =>
      interventionFixture({
        status: 'en_cours',
        agreedAmountFcfa: 12_000,
        payment,
        canOpenDispute: true,
      });

    function renderCard(intervention: Intervention, role: 'client' | 'artisan') {
      return render(
        <MemoryRouter>
          <InterventionCard intervention={intervention} role={role} onChanged={onChanged} />
        </MemoryRouter>,
      );
    }

    beforeEach(() => {
      mockedApi.cancelIntervention.mockReset().mockResolvedValue(interventionFixture({}));
      mockedApi.openDispute.mockReset().mockResolvedValue(interventionFixture({}));
    });

    it('invite le client à payer le devis accepté', () => {
      renderCard(inProgress(), 'client');

      expect(screen.getByRole('link', { name: 'Payer 12 000 FCFA' })).toHaveAttribute(
        'href',
        '/paiement/int-1',
      );
      expect(
        screen.getByText(/Sans paiement en ligne, vous réglez l'artisan directement/),
      ).toBeInTheDocument();
    });

    it("bloque la fin des travaux tant qu'un paiement en ligne est en cours", () => {
      renderCard(
        inProgress(
          paymentFixture({ status: 'en_attente', channel: 'wave', checkoutUrl: 'https://x/c' }),
        ),
        'client',
      );

      expect(screen.getByRole('button', { name: 'Confirmer la fin des travaux' })).toBeDisabled();
      expect(screen.getByText(/terminez-le avant de confirmer/)).toBeInTheDocument();
    });

    it('rappelle au client que confirmer la fin verse le séquestre', () => {
      renderCard(inProgress(paymentFixture({ status: 'retenu', channel: 'wave' })), 'client');

      expect(
        screen.getByText(/Confirmer la fin des travaux verse le paiement/),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Confirmer la fin des travaux' })).toBeEnabled();
    });

    it("ne laisse pas le client annuler seul une fois l'argent en séquestre, mais lui permet de signaler un problème", () => {
      renderCard(inProgress(paymentFixture({ status: 'retenu', channel: 'wave' })), 'client');

      expect(screen.queryByRole('button', { name: 'Annuler' })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Signaler un problème' })).toBeInTheDocument();
    });

    it("l'artisan annule en sachant que le client sera remboursé", async () => {
      renderCard(inProgress(paymentFixture({ status: 'retenu', channel: 'wave' })), 'artisan');

      fireEvent.click(screen.getByRole('button', { name: 'Annuler' }));
      expect(screen.getByText(/client sera intégralement remboursé/)).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText("Motif de l'annulation"), {
        target: { value: 'Pièce introuvable.' },
      });
      fireEvent.click(screen.getByRole('button', { name: "Confirmer l'annulation" }));

      await waitFor(() =>
        expect(mockedApi.cancelIntervention).toHaveBeenCalledWith('int-1', 'Pièce introuvable.'),
      );
      await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    });

    it('un litige exige une description, puis est envoyé', async () => {
      renderCard(inProgress(paymentFixture({ status: 'retenu', channel: 'wave' })), 'client');

      fireEvent.click(screen.getByRole('button', { name: 'Signaler un problème' }));
      const send = screen.getByRole('button', { name: 'Envoyer le signalement' });
      fireEvent.change(screen.getByLabelText('Description du problème'), {
        target: { value: 'Trop court' },
      });
      expect(send).toBeEnabled();
      fireEvent.change(screen.getByLabelText('Description du problème'), {
        target: { value: 'Court' },
      });
      expect(send).toBeDisabled();
      fireEvent.change(screen.getByLabelText('Description du problème'), {
        target: { value: 'La fuite continue après les travaux.' },
      });
      fireEvent.click(send);

      await waitFor(() =>
        expect(mockedApi.openDispute).toHaveBeenCalledWith(
          'int-1',
          'La fuite continue après les travaux.',
        ),
      );
    });

    it("explique le litige en cours et le gel de l'argent", () => {
      renderCard(
        interventionFixture({
          status: 'litige',
          agreedAmountFcfa: 12_000,
          payment: paymentFixture({ status: 'retenu', channel: 'wave' }),
          dispute: {
            openedBy: 'client',
            reason: 'La fuite continue.',
            openedAt: '2026-10-11T10:00:00Z',
            outcome: null,
            resolvedAt: null,
            resolutionNote: null,
          },
        }),
        'artisan',
      );

      expect(screen.getByText('Problème signalé par le client')).toBeInTheDocument();
      expect(screen.getByText(/L'argent est gelé/)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Annuler' })).not.toBeInTheDocument();
    });

    it("dit qui a annulé et comment l'argent a été rendu", () => {
      renderCard(
        interventionFixture({
          status: 'annulee',
          agreedAmountFcfa: 12_000,
          cancellation: {
            kind: 'annulation',
            by: 'artisan',
            reason: 'Pièce introuvable.',
            at: '2026-10-11T10:00:00Z',
          },
          payment: paymentFixture({ status: 'rembourse', channel: 'wave' }),
        }),
        'client',
      );

      expect(
        screen.getByText("L'artisan a annulé cette mise en relation. Motif : Pièce introuvable."),
      ).toBeInTheDocument();
      expect(screen.getByText('Remboursé')).toBeInTheDocument();
    });

    const arbitrated = (payment: ReturnType<typeof paymentFixture> | null) =>
      interventionFixture({
        status: 'annulee',
        agreedAmountFcfa: 12_000,
        payment,
        cancellation: {
          kind: 'arbitrage',
          by: 'admin',
          reason: 'Non réalisé.',
          at: '2026-10-11T10:00:00Z',
        },
      });

    it('annonce un remboursement seulement quand le séquestre a été rendu', () => {
      renderCard(arbitrated(paymentFixture({ status: 'rembourse', channel: 'wave' })), 'artisan');

      expect(
        screen.getByText(/Litige tranché par Téranga : le client a été remboursé/),
      ).toBeInTheDocument();
    });

    it('en espèces, jamais de « remboursement » que Téranga ne peut pas faire', () => {
      renderCard(arbitrated(paymentFixture({ status: 'reussi', channel: 'cash' })), 'client');

      expect(screen.getByText(/en faveur du client : aucune commission n'est due/)).toBeVisible();
      expect(screen.getByText(/ne peut pas les rembourser/)).toBeVisible();
      expect(screen.queryByText(/a été remboursé/)).not.toBeInTheDocument();
    });

    it('sans aucun paiement, la décision est dite sans parler d’argent', () => {
      renderCard(arbitrated(null), 'artisan');

      expect(
        screen.getByText(/en faveur du client : aucune commission n'est due\.$/),
      ).toBeVisible();
    });

    it('en espèces, un litige en cours est une médiation, jamais « argent gelé »', () => {
      renderCard(
        interventionFixture({
          status: 'litige',
          agreedAmountFcfa: 12_000,
          payment: paymentFixture({ status: 'reussi', channel: 'cash' }),
          dispute: {
            openedBy: 'artisan',
            reason: 'Le client ne confirme pas la fin.',
            openedAt: '2026-10-11T10:00:00Z',
            outcome: null,
            resolvedAt: null,
            resolutionNote: null,
          },
        }),
        'client',
      );

      expect(screen.getByText(/examine la situation \(médiation\)/)).toBeVisible();
      expect(screen.queryByText(/gelé/)).not.toBeInTheDocument();
    });

    it('après des travaux reconnus en espèces, rien n’est dit « versé »', () => {
      renderCard(
        interventionFixture({
          status: 'terminee',
          agreedAmountFcfa: 12_000,
          payment: paymentFixture({ status: 'reussi', channel: 'cash' }),
          dispute: {
            openedBy: 'client',
            reason: 'Joint qui fuit.',
            openedAt: '2026-10-11T10:00:00Z',
            outcome: 'libere',
            resolvedAt: '2026-10-12T10:00:00Z',
            resolutionNote: 'Photos examinées.',
          },
        }),
        'client',
      );

      expect(screen.getByText(/Litige clos par Téranga : travaux reconnus/)).toBeVisible();
      expect(screen.queryByText(/versé/)).not.toBeInTheDocument();
    });
  });

  describe('encart « Un souci ? »', () => {
    function renderCard(intervention: Intervention, role: 'client' | 'artisan') {
      return render(
        <MemoryRouter>
          <InterventionCard intervention={intervention} role={role} onChanged={onChanged} />
        </MemoryRouter>,
      );
    }

    it("après les travaux, propose de signaler un problème jusqu'à la limite donnée par le serveur", () => {
      renderCard(
        interventionFixture({
          status: 'terminee',
          agreedAmountFcfa: 12_000,
          completedAt: '2026-10-10T10:00:00Z',
          canOpenDispute: true,
          disputeDeadline: '2026-10-13T10:00:00Z',
          payment: paymentFixture({ status: 'reussi', channel: 'cash' }),
        }),
        'client',
      );

      const box = screen.getByRole('region', { name: 'Un souci ?' });
      expect(within(box).getByText(/Vous pouvez le signaler jusqu'au 13 octobre/)).toBeVisible();
      fireEvent.click(within(box).getByRole('button', { name: 'Signaler un problème' }));
      expect(screen.getByText(/ne peut pas les rembourser/)).toBeVisible();
    });

    it("délai dépassé (le serveur refuse) : plus de signalement, mais l'aide avec l'intervention", () => {
      renderCard(
        interventionFixture({
          status: 'terminee',
          agreedAmountFcfa: 12_000,
          completedAt: '2026-10-01T10:00:00Z',
          canOpenDispute: false,
          disputeDeadline: null,
        }),
        'client',
      );

      const box = screen.getByRole('region', { name: 'Un souci ?' });
      expect(within(box).queryByRole('button', { name: 'Signaler un problème' })).toBeNull();
      expect(within(box).getByText(/n'est plus possible/)).toBeVisible();
      expect(within(box).getByRole('link', { name: "Contacter l'aide" })).toHaveAttribute(
        'href',
        '/aide?intervention=int-1',
      );
    });

    it("intervention annulée : l'aide reste joignable", () => {
      renderCard(
        interventionFixture({
          status: 'annulee',
          cancellation: { kind: 'refus', by: 'artisan', reason: null, at: '2026-10-11T10:00:00Z' },
        }),
        'artisan',
      );

      expect(screen.getByRole('link', { name: "Contacter l'aide" })).toHaveAttribute(
        'href',
        '/aide?intervention=int-1',
      );
    });

    it("tant que le signalement est possible, pas de lien d'aide à sa place", () => {
      renderCard(
        interventionFixture({
          status: 'terminee',
          agreedAmountFcfa: 12_000,
          canOpenDispute: true,
          disputeDeadline: '2026-10-13T10:00:00Z',
        }),
        'client',
      );

      expect(screen.queryByRole('link', { name: "Contacter l'aide" })).toBeNull();
      expect(screen.getByRole('button', { name: 'Signaler un problème' })).toBeVisible();
    });

    it("avant les travaux, explique qu'on peut annuler", () => {
      renderCard(interventionFixture({ status: 'acceptee' }), 'client');

      const box = screen.getByRole('region', { name: 'Un souci ?' });
      expect(within(box).getByText(/Les travaux n'ont pas commencé/)).toBeVisible();
      expect(within(box).getByRole('button', { name: 'Annuler' })).toBeVisible();
      expect(within(box).queryByRole('button', { name: 'Signaler un problème' })).toBeNull();
    });

    it('pendant les travaux, le signalement est mis en avant', () => {
      renderCard(
        interventionFixture({ status: 'en_cours', agreedAmountFcfa: 12_000, canOpenDispute: true }),
        'artisan',
      );

      const box = screen.getByRole('region', { name: 'Un souci ?' });
      expect(within(box).getByText(/Un problème pendant les travaux/)).toBeVisible();
      expect(within(box).getByRole('button', { name: 'Signaler un problème' })).toBeVisible();
    });
  });
});
