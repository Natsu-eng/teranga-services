import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AdminCommissionsScreen } from './AdminCommissionsScreen';
import { percentToBps } from './adminText';
import { api } from '../../lib/api';
import type { CommissionGrid } from '../../types/admin';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getCommissionGrid: vi.fn(),
      addCommissionRate: vi.fn(),
      listTrades: vi.fn(),
    },
  };
});

const mockedApi = vi.mocked(api, true);

const grid: CommissionGrid = {
  maxRateBps: 3000,
  generatedAt: '2026-10-12T10:00:00Z',
  items: [
    {
      id: 'rate-global',
      rateBps: 1000,
      tradeCode: null,
      tradeLabel: null,
      effectiveFrom: '2026-01-01T00:00:00Z',
      effectiveTo: null,
      state: 'en_vigueur',
      interventionsCount: 12,
      createdAt: '2026-01-01T00:00:00Z',
    },
  ],
};

function renderScreen() {
  return render(
    <MemoryRouter>
      <AdminCommissionsScreen />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('percentToBps', () => {
  it('convertit un pourcentage français en points de base, sans arrondi caché', () => {
    expect(percentToBps('10')).toBe(1000);
    expect(percentToBps('7,5')).toBe(750);
    expect(percentToBps('12.25')).toBe(1225);
    expect(percentToBps('1.234')).toBeNull();
    expect(percentToBps('-1')).toBeNull();
    expect(percentToBps('dix')).toBeNull();
  });
});

describe('AdminCommissionsScreen', () => {
  it('explique que les taux passés sont figés et affiche la grille', async () => {
    mockedApi.getCommissionGrid.mockResolvedValue(grid);
    mockedApi.listTrades.mockResolvedValue([]);

    renderScreen();

    expect(screen.getByText('Les taux passés ne bougent jamais')).toBeInTheDocument();
    expect(await screen.findByText('12 interventions ont figé ce taux.')).toBeInTheDocument();
    expect(screen.getByText('En vigueur')).toBeInTheDocument();
  });

  it('refuse un taux au-delà du plafond avant tout envoi', async () => {
    mockedApi.getCommissionGrid.mockResolvedValue(grid);
    mockedApi.listTrades.mockResolvedValue([]);

    renderScreen();
    await screen.findByText('12 interventions ont figé ce taux.');
    fireEvent.change(screen.getByLabelText('Taux (%)'), { target: { value: '45' } });

    expect(screen.getByText('Le plafond de saisie est de 30 %.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Vérifier et ajouter' })).toBeDisabled();
  });

  it('récapitule l’effet (taux actuel clos, interventions intactes) puis ajoute', async () => {
    mockedApi.getCommissionGrid.mockResolvedValue(grid);
    mockedApi.listTrades.mockResolvedValue([]);
    mockedApi.addCommissionRate.mockResolvedValue({
      ...grid.items[0],
      id: 'rate-new',
      rateBps: 1250,
      interventionsCount: 0,
    });

    renderScreen();
    await screen.findByText('12 interventions ont figé ce taux.');
    fireEvent.change(screen.getByLabelText('Taux (%)'), { target: { value: '12,5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Vérifier et ajouter' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Le taux actuel \(10 %\) se terminera/)).toBeInTheDocument();
    expect(within(dialog).getByText(/gardent leur taux/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ajouter le taux' }));

    await waitFor(() =>
      expect(mockedApi.addCommissionRate).toHaveBeenCalledWith({
        rateBps: 1250,
        tradeCode: null,
        effectiveFrom: null,
        note: '',
      }),
    );
    expect(await screen.findByText(/Taux de 12,5 % ajouté/)).toBeInTheDocument();
    expect(mockedApi.getCommissionGrid).toHaveBeenCalledTimes(2);
  });
});
