import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { EarningsScreen } from './EarningsScreen';
import { api } from '../../lib/api';
import type { PaymentOptions } from '../../types';
import { paymentFixture } from './paymentFixtures';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getMyEarnings: vi.fn(),
      getPaymentOptions: vi.fn(),
      getPayoutSettings: vi.fn(),
      updatePayoutSettings: vi.fn(),
    },
  };
});

const mockedApi = vi.mocked(api, true);

// Configuration réelle lue par l'écran (GET /payments/options).
const ONLINE: PaymentOptions = {
  onlineChannels: ['wave', 'orange_money', 'carte'],
  upcomingChannels: [],
  cashEnabled: true,
  currency: 'XOF',
};
const CASH_ONLY: PaymentOptions = {
  onlineChannels: [],
  upcomingChannels: ['wave', 'orange_money', 'carte'],
  cashEnabled: true,
  currency: 'XOF',
};

function renderScreen() {
  return render(
    <MemoryRouter>
      <EarningsScreen />
    </MemoryRouter>,
  );
}

describe('EarningsScreen', () => {
  beforeEach(() => {
    mockedApi.getMyEarnings.mockReset().mockResolvedValue({
      totals: {
        paidOutFcfa: 10_800,
        payoutPendingFcfa: 0,
        inEscrowFcfa: 4_500,
        commissionCollectedFcfa: 1_200,
        cashReceivedFcfa: 20_000,
        commissionDueFcfa: 2_000,
      },
      items: [
        {
          interventionId: 'int-1',
          tradeLabel: 'Plomberie',
          clientName: 'Awa Diop',
          interventionStatus: 'terminee',
          payment: paymentFixture({
            status: 'libere',
            channel: 'wave',
            commission: { rateBps: 1000, amountFcfa: 1_200, status: 'collectee' },
            payout: { status: 'envoye', amountFcfa: 10_800, channel: 'wave', sentAt: null },
          }),
        },
      ],
    });
    mockedApi.getPayoutSettings.mockReset().mockResolvedValue({
      channel: 'wave',
      chosen: false,
      allowedChannels: ['wave', 'orange_money'],
      destinationPhone: '+221770000001',
    });
    mockedApi.updatePayoutSettings.mockReset().mockResolvedValue({
      channel: 'orange_money',
      chosen: true,
      allowedChannels: ['wave', 'orange_money'],
      destinationPhone: '+221770000001',
    });
  });
  beforeEach(() => {
    // Par défaut : paiement en ligne actif (versements, séquestre).
    mockedApi.getPaymentOptions.mockReset().mockResolvedValue(ONLINE);
  });
  afterEach(cleanup);

  it('en mode espèces : seulement les espèces encaissées et la commission due', async () => {
    mockedApi.getPaymentOptions.mockResolvedValue(CASH_ONLY);
    renderScreen();

    expect(await screen.findByText('Espèces encaissées')).toBeInTheDocument();
    expect(screen.getByText('Commission due')).toBeInTheDocument();
    // Rien qui présenterait le paiement en ligne comme actif.
    for (const label of ['Versé sur votre compte', 'En séquestre', 'Commissions prélevées']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
    expect(screen.queryByText('Mes versements')).not.toBeInTheDocument();
    expect(mockedApi.getPayoutSettings).not.toHaveBeenCalled();
    expect(screen.queryByText(/déduisent automatiquement/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/la commission de Téranga \(2 000 FCFA\) reste due/),
    ).toBeInTheDocument();
  });

  it('résume ce qui est versé, en séquestre, prélevé et dû', async () => {
    renderScreen();

    expect(await screen.findByText('Versé sur votre compte')).toBeInTheDocument();
    expect(screen.getAllByText('10 800 FCFA').length).toBeGreaterThan(0);
    expect(screen.getByText('4 500 FCFA')).toBeInTheDocument();
    expect(screen.getByText('Commissions prélevées')).toBeInTheDocument();
    expect(screen.getByText('20 000 FCFA')).toBeInTheDocument();
    expect(
      screen.getByText(/la commission de Téranga \(2 000 FCFA\) reste due/),
    ).toBeInTheDocument();
  });

  it('détaille chaque intervention : prix, commission, net', async () => {
    renderScreen();

    const item = (await screen.findByText('Plomberie')).closest('li') as HTMLElement;
    expect(within(item).getByText('Client : Awa Diop · Wave')).toBeInTheDocument();
    expect(within(item).getByText('12 000 FCFA')).toBeInTheDocument();
    expect(within(item).getByText('− 1 200 FCFA')).toBeInTheDocument();
    expect(within(item).getByText('Vous recevez')).toBeInTheDocument();
    expect(within(item).getByText('Versé')).toBeInTheDocument();
  });

  it('change le moyen de versement, toujours vers le numéro vérifié du compte', async () => {
    renderScreen();

    expect(await screen.findByText(/numéro de votre compte, \+221770000001/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Orange Money' }));

    await waitFor(() =>
      expect(mockedApi.updatePayoutSettings).toHaveBeenCalledWith('orange_money'),
    );
    expect(await screen.findByRole('radio', { name: 'Orange Money' })).toBeChecked();
    // Aucun champ pour saisir un autre numéro.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
