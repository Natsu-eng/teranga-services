import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MyReviewsSection } from './MyReviewsSection';
import { api } from '../../lib/api';
import type { MyReceivedReview } from '../../types';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, api: { ...actual.api, listMyReviews: vi.fn(), reportReview: vi.fn() } };
});

const mockedApi = vi.mocked(api, true);

const REASON = 'Ce client ne m’a jamais fait appel.';

const published: MyReceivedReview = {
  id: 'rev-1',
  rating: 1,
  comment: 'À fuir.',
  authorName: 'Awa D.',
  createdAt: '2026-01-01T10:00:00Z',
  status: 'publie',
  reportReason: null,
  reportedAt: null,
  canReport: true,
};

const hidden: MyReceivedReview = {
  ...published,
  id: 'rev-2',
  comment: 'Propos injurieux.',
  status: 'masque',
  canReport: false,
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('MyReviewsSection', () => {
  it('montre la décision de modération et permet un signalement motivé, une seule fois', async () => {
    mockedApi.listMyReviews.mockResolvedValue([published, hidden]);
    mockedApi.reportReview.mockResolvedValue({
      ...published,
      status: 'signale',
      reportReason: REASON,
      reportedAt: '2026-10-12T10:00:00Z',
      canReport: false,
    });

    render(<MyReviewsSection />);

    expect(await screen.findByText('Masqué par la modération')).toBeInTheDocument();
    const reportButtons = screen.getAllByRole('button', { name: /Signaler cet avis/ });
    expect(reportButtons).toHaveLength(1);
    fireEvent.click(reportButtons[0]);
    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText(/l’avis reste visible et compte dans votre note/),
    ).toBeInTheDocument();
    const send = within(dialog).getByRole('button', { name: 'Envoyer le signalement' });
    expect(send).toBeDisabled();
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: REASON } });
    fireEvent.click(send);

    await waitFor(() => expect(mockedApi.reportReview).toHaveBeenCalledWith('rev-1', REASON));
    expect(await screen.findByText('Signalé · en cours d’examen')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Signaler cet avis/ })).not.toBeInTheDocument();
  });
});
