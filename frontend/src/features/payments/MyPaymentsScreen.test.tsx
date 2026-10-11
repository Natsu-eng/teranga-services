import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { MyPaymentsScreen } from './MyPaymentsScreen';
import { api } from '../../lib/api';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, api: { ...actual.api, listMyPayments: vi.fn() } };
});

const mockedApi = vi.mocked(api, true);

function renderScreen() {
  return render(
    <MemoryRouter>
      <MyPaymentsScreen />
    </MemoryRouter>,
  );
}

describe('MyPaymentsScreen', () => {
  beforeEach(() => mockedApi.listMyPayments.mockReset());
  afterEach(cleanup);

  it('liste les paiements avec leur état et la date qui compte', async () => {
    mockedApi.listMyPayments.mockResolvedValue([
      {
        id: 'p1',
        interventionId: 'int-1',
        tradeLabel: 'Plomberie',
        artisanName: 'Idrissa Fall',
        amountFcfa: 12_000,
        channel: 'wave',
        status: 'retenu',
        createdAt: '2026-10-10T09:00:00Z',
        paidAt: '2026-10-10T09:05:00Z',
        releasedAt: null,
        refundedAt: null,
      },
      {
        id: 'p2',
        interventionId: 'int-2',
        tradeLabel: 'Électricité',
        artisanName: 'Maty Ndiaye',
        amountFcfa: 8_000,
        channel: 'orange_money',
        status: 'rembourse',
        createdAt: '2026-10-09T09:00:00Z',
        paidAt: '2026-10-09T09:05:00Z',
        releasedAt: null,
        refundedAt: '2026-10-11T09:00:00Z',
      },
    ]);
    renderScreen();

    expect(await screen.findByText('Plomberie · Idrissa Fall')).toBeInTheDocument();
    expect(screen.getByText('En séquestre')).toBeInTheDocument();
    expect(screen.getByText('Wave · Payé le 10 octobre 2026')).toBeInTheDocument();
    expect(screen.getByText('Remboursé')).toBeInTheDocument();
    expect(screen.getByText('Orange Money · Remboursé le 11 octobre 2026')).toBeInTheDocument();
    expect(screen.getByText(/Aucun frais ne s'ajoute au prix du devis/)).toBeInTheDocument();
  });

  it('guide le client sans paiement', async () => {
    mockedApi.listMyPayments.mockResolvedValue([]);
    renderScreen();

    expect(await screen.findByText('Aucun paiement pour le moment.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voir mes devis et travaux' })).toHaveAttribute(
      'href',
      '/mes-interventions',
    );
  });
});
