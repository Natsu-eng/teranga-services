import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { PaymentScreen, CONFIRMATION_POLL_MS } from './PaymentScreen';
import { ApiError, api } from '../../lib/api';
import { navigateToExternal } from '../../lib/externalNavigation';
import { payableInterventionFixture, paymentFixture } from './paymentFixtures';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getInterventionById: vi.fn(),
      getPaymentOptions: vi.fn(),
      initPayment: vi.fn(),
    },
  };
});
vi.mock('../../lib/externalNavigation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/externalNavigation')>();
  return { ...actual, navigateToExternal: vi.fn() };
});

const mockedApi = vi.mocked(api, true);
const mockedNavigate = vi.mocked(navigateToExternal);

function renderScreen(path = '/paiement/int-1') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/paiement/:interventionId" element={<PaymentScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PaymentScreen', () => {
  beforeEach(() => {
    mockedApi.getInterventionById.mockReset().mockResolvedValue(payableInterventionFixture());
    mockedApi.getPaymentOptions.mockReset().mockResolvedValue({
      onlineChannels: ['wave', 'orange_money', 'carte'],
      upcomingChannels: [],
      cashEnabled: true,
      currency: 'XOF',
    });
    mockedApi.initPayment.mockReset();
    mockedNavigate.mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('affiche un récapitulatif transparent : total du devis, aucun frais ajouté, séquestre', async () => {
    renderScreen();

    expect(await screen.findByText('Total à payer')).toBeInTheDocument();
    expect(screen.getByText('12 000 FCFA')).toBeInTheDocument();
    expect(screen.getByText(/Aucun frais ajouté pour vous/)).toBeInTheDocument();
    expect(screen.getByText(/commission de Téranga \(10 %\)/)).toBeInTheDocument();
    expect(screen.getByText(/Téranga conserve votre argent/)).toBeInTheDocument();
    // Le client ne voit pas une « part artisan » ambiguë à la place du total.
    expect(screen.queryByText('Vous recevez')).not.toBeInTheDocument();
    for (const name of [/Wave/, /Orange Money/, /Carte bancaire/, /Espèces/]) {
      expect(screen.getByRole('radio', { name })).toBeInTheDocument();
    }
  });

  it('ouvre la page du fournisseur sans jamais envoyer de montant', async () => {
    mockedApi.initPayment.mockResolvedValue(
      paymentFixture({
        status: 'en_attente',
        channel: 'orange_money',
        checkoutUrl: 'https://paiement.exemple/checkout/abc',
      }),
    );
    renderScreen();

    fireEvent.click(await screen.findByRole('radio', { name: /Orange Money/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Payer 12 000 FCFA avec Orange Money' }));

    await waitFor(() =>
      expect(mockedNavigate).toHaveBeenCalledWith('https://paiement.exemple/checkout/abc'),
    );
    expect(mockedApi.initPayment).toHaveBeenCalledWith('int-1', 'orange_money');
  });

  it('enregistre un paiement en espèces et dit clairement ce qu’il implique', async () => {
    mockedApi.initPayment.mockResolvedValue(paymentFixture({ status: 'reussi', channel: 'cash' }));
    renderScreen();

    fireEvent.click(await screen.findByRole('radio', { name: /Espèces/ }));
    mockedApi.getInterventionById.mockResolvedValue(
      payableInterventionFixture({
        payment: paymentFixture({ status: 'reussi', channel: 'cash' }),
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Je paierai 12 000 FCFA en espèces' }));

    expect(await screen.findByText('Paiement en espèces enregistré')).toBeInTheDocument();
    expect(screen.getByText(/pas protégé par le séquestre/)).toBeInTheDocument();
    expect(mockedApi.initPayment).toHaveBeenCalledWith('int-1', 'cash');
    expect(mockedNavigate).not.toHaveBeenCalled();
    // Le paiement protégé reste possible.
    fireEvent.click(screen.getByRole('button', { name: 'Payer en ligne plutôt' }));
    expect(screen.queryByRole('radio', { name: /Espèces/ })).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Wave/ })).toBeInTheDocument();
  });

  it("explique l'échec d'un paiement et permet de réessayer", async () => {
    renderScreen('/paiement/int-1?retour=echec');

    expect(await screen.findByRole('alert')).toHaveTextContent(/aucun montant n'a été prélevé/);
    expect(screen.getByRole('button', { name: /Payer 12 000 FCFA/ })).toBeInTheDocument();
  });

  it('attend la confirmation au retour du fournisseur, puis affiche le séquestre', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockedApi.getInterventionById.mockResolvedValue(
      payableInterventionFixture({
        payment: paymentFixture({
          status: 'en_attente',
          channel: 'wave',
          checkoutUrl: 'https://paiement.exemple/checkout/abc',
        }),
      }),
    );
    renderScreen('/paiement/int-1?retour=succes');

    expect(await screen.findByText('Confirmation du paiement…')).toBeInTheDocument();

    mockedApi.getInterventionById.mockResolvedValue(
      payableInterventionFixture({
        payment: paymentFixture({
          status: 'retenu',
          channel: 'wave',
          paidAt: '2026-10-11T10:00:00Z',
        }),
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(CONFIRMATION_POLL_MS);
    });

    expect(await screen.findByText('Paiement reçu')).toBeInTheDocument();
    expect(
      screen.getByText(/ne seront versés à l'artisan que lorsque vous confirmerez/),
    ).toBeInTheDocument();
  });

  it('affiche le refus du serveur sans quitter la page', async () => {
    mockedApi.initPayment.mockRejectedValue(
      new ApiError('validation', 'Ce moyen de paiement n’est pas disponible pour le moment.'),
    );
    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: /Payer 12 000 FCFA avec Wave/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/pas disponible/);
    expect(mockedNavigate).not.toHaveBeenCalled();
  });

  it("n'expose rien d'un paiement qui n'est pas le sien", async () => {
    mockedApi.getInterventionById.mockRejectedValue(
      new ApiError('forbidden', "Vous n'avez pas accès à cette intervention."),
    );
    renderScreen();

    expect(await screen.findByText('Ce paiement est introuvable.')).toBeInTheDocument();
    expect(screen.queryByText(/FCFA/)).not.toBeInTheDocument();
  });

  it('ne propose rien à payer avant un devis accepté', async () => {
    mockedApi.getInterventionById.mockResolvedValue(
      payableInterventionFixture({ status: 'acceptee', payment: null, quote: null }),
    );
    renderScreen();

    expect(await screen.findByText('Rien à payer pour le moment.')).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it("n'affiche que les moyens réellement proposés par le serveur", async () => {
    mockedApi.getPaymentOptions.mockResolvedValue({
      onlineChannels: [],
      upcomingChannels: ['wave', 'orange_money', 'carte'],
      cashEnabled: true,
      currency: 'XOF',
    });
    renderScreen();

    expect(await screen.findByRole('radio', { name: /Espèces/ })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /Wave/ })).not.toBeInTheDocument();
  });

  it('lancement espèces seulement : aucune promesse de séquestre, le cash fonctionne', async () => {
    mockedApi.getPaymentOptions.mockResolvedValue({
      onlineChannels: [],
      upcomingChannels: ['wave', 'orange_money', 'carte'],
      cashEnabled: true,
      currency: 'XOF',
    });
    mockedApi.initPayment.mockResolvedValue(
      paymentFixture({ status: 'reussi', channel: 'cash', onlineAvailable: false }),
    );
    renderScreen();

    expect(
      await screen.findByText(/Le paiement en ligne n.est pas encore disponible/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Paiement en ligne protégé/)).not.toBeInTheDocument();
    expect(screen.queryByText(/séquestre/)).not.toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Je paierai 12 000 FCFA en espèces' }));

    await waitFor(() => expect(mockedApi.initPayment).toHaveBeenCalledWith('int-1', 'cash'));
    expect(mockedNavigate).not.toHaveBeenCalled();
  });
});
