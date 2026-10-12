import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AdminReviewsScreen } from './AdminReviewsScreen';
import { api } from '../../lib/api';
import type { AdminReview, PageResult } from '../../types/admin';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, listAdminReviews: vi.fn(), hideReview: vi.fn(), restoreReview: vi.fn() },
  };
});

const mockedApi = vi.mocked(api, true);

const reported: AdminReview = {
  id: 'rev-1',
  rating: 1,
  comment: 'Travail bâclé, à fuir.',
  status: 'signale',
  contactVerified: true,
  createdAt: '2026-01-01T10:00:00Z',
  interventionId: 'int-1',
  authorId: 'u-1',
  authorName: 'Awa Diop',
  artisanId: 'art-1',
  artisanName: 'Idrissa Fall',
  reportReason: 'Ce client ne m’a jamais fait appel.',
  reportedAt: '2026-01-02T10:00:00Z',
};

function page(items: AdminReview[]): PageResult<AdminReview> {
  return { items, page: 1, total: items.length, totalPages: 1 };
}

function renderScreen() {
  return render(
    <MemoryRouter>
      <AdminReviewsScreen />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('AdminReviewsScreen', () => {
  it('ouvre sur les avis signalés, avec le motif du signalement et l’auteur réel', async () => {
    mockedApi.listAdminReviews.mockResolvedValue(page([reported]));

    renderScreen();

    expect(await screen.findByText(/Ce client ne m’a jamais fait appel/)).toBeInTheDocument();
    expect(screen.getByText(/Awa Diop/)).toBeInTheDocument();
    expect(mockedApi.listAdminReviews).toHaveBeenCalledWith({ status: 'signale', q: '', page: 1 });
    expect(screen.getByRole('button', { name: /Maintenir l’avis/ })).toBeInTheDocument();
  });

  it('exige un motif pour masquer, puis affiche le nouveau statut', async () => {
    mockedApi.listAdminReviews.mockResolvedValue(page([reported]));
    mockedApi.hideReview.mockResolvedValue({ ...reported, status: 'masque' });

    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: /Masquer/ }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Masquer l’avis' });
    fireEvent.change(within(dialog).getByLabelText('Motif du masquage'), {
      target: { value: 'Court' },
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('Motif du masquage'), {
      target: { value: 'Avis sans rapport avec l’intervention.' },
    });
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(mockedApi.hideReview).toHaveBeenCalledWith(
        'rev-1',
        'Avis sans rapport avec l’intervention.',
      ),
    );
    expect(await screen.findByText('Masqué')).toBeInTheDocument();
    // Un avis masqué se rétablit, il ne se supprime jamais.
    expect(screen.getByRole('button', { name: /Rétablir/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Supprimer/ })).not.toBeInTheDocument();
  });
});
