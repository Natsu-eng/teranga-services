import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AdminDisputesScreen } from './AdminDisputesScreen';
import { api } from '../../lib/api';
import { useAuth } from '../auth/hooks/useAuth';
import type { AuthContextValue } from '../auth/auth-context';
import { payableInterventionFixture, paymentFixture } from '../payments/paymentFixtures';

vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, listAdminDisputes: vi.fn(), resolveDispute: vi.fn() },
  };
});

const mockedApi = vi.mocked(api, true);

const disputed = payableInterventionFixture({
  status: 'litige',
  payment: paymentFixture({
    status: 'retenu',
    channel: 'wave',
    commission: { rateBps: 1000, amountFcfa: 1_200, status: 'due' },
  }),
  dispute: {
    openedBy: 'artisan',
    reason: 'Le client ne confirme pas la fin des travaux.',
    openedAt: '2026-10-11T10:00:00Z',
    outcome: null,
    resolvedAt: null,
    resolutionNote: null,
  },
});

function renderScreen() {
  return render(
    <MemoryRouter>
      <AdminDisputesScreen />
    </MemoryRouter>,
  );
}

describe('AdminDisputesScreen', () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({ logout: vi.fn() } as unknown as AuthContextValue);
    mockedApi.listAdminDisputes.mockReset().mockResolvedValue([disputed]);
    mockedApi.resolveDispute.mockReset().mockResolvedValue(disputed);
  });
  afterEach(cleanup);

  it('présente le motif et les montants gelés', async () => {
    renderScreen();

    expect(
      await screen.findByText('Le client ne confirme pas la fin des travaux.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Signalé par l'artisan le 11 octobre 2026/)).toBeInTheDocument();
    expect(screen.getByText('12 000 FCFA en séquestre')).toBeInTheDocument();
    expect(screen.getByText('Commission (10 %)')).toBeInTheDocument();
    expect(screen.getByText('10 800 FCFA')).toBeInTheDocument();
  });

  it('tranche avec une justification obligatoire, puis retire le litige de la file', async () => {
    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: "Verser à l'artisan" }));
    const confirm = screen.getByRole('button', { name: 'Confirmer la décision' });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Justification (visible des deux parties)'), {
      target: { value: 'Photos des travaux terminés fournies.' },
    });
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(mockedApi.resolveDispute).toHaveBeenCalledWith(
        'int-1',
        'libere',
        'Photos des travaux terminés fournies.',
      ),
    );
    expect(await screen.findByText('Aucun litige à trancher.')).toBeInTheDocument();
  });

  it('en espèces, propose une médiation et jamais un remboursement par Téranga', async () => {
    mockedApi.listAdminDisputes.mockResolvedValue([
      { ...disputed, payment: paymentFixture({ status: 'reussi', channel: 'cash' }) },
    ]);
    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: 'Clore en faveur du client' }));

    expect(screen.queryByRole('button', { name: 'Rembourser le client' })).toBeNull();
    expect(screen.getByText(/aucun remboursement n'est effectué par Téranga/)).toBeVisible();
  });

  it('un litige tranché en espèces est étiqueté selon ce qui a été fait', async () => {
    mockedApi.listAdminDisputes.mockResolvedValue([
      {
        ...disputed,
        status: 'annulee',
        payment: paymentFixture({ status: 'reussi', channel: 'cash' }),
        dispute: {
          ...disputed.dispute!,
          outcome: 'rembourse',
          resolvedAt: '2026-10-12T10:00:00Z',
          resolutionNote: 'Travaux non réalisés.',
        },
      },
    ]);
    renderScreen();

    expect(await screen.findByText('Clos en faveur du client')).toBeVisible();
    expect(screen.queryByText('Client remboursé')).toBeNull();
  });

  it('affiche les litiges déjà tranchés', async () => {
    renderScreen();
    await screen.findByText('Le client ne confirme pas la fin des travaux.');

    fireEvent.click(screen.getByRole('button', { name: 'Tranchés' }));

    await waitFor(() =>
      expect(mockedApi.listAdminDisputes).toHaveBeenLastCalledWith({ resolved: true }),
    );
  });
});
