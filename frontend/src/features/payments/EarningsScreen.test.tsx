import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { EarningsScreen } from './EarningsScreen';
import { api } from '../../lib/api';
import { paymentFixture } from './paymentFixtures';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getMyEarnings: vi.fn(),
      getPayoutSettings: vi.fn(),
      updatePayoutSettings: vi.fn(),
    },
  };
});

const mockedApi = vi.mocked(api, true);

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
  afterEach(cleanup);

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
