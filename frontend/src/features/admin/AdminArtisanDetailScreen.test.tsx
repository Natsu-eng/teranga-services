import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { AdminArtisanDetailScreen } from './AdminArtisanDetailScreen';
import { api } from '../../lib/api';
import type { AdminArtisanDetail } from '../../types/admin';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getAdminArtisan: vi.fn(),
      suspendArtisan: vi.fn(),
      reactivateArtisan: vi.fn(),
    },
  };
});

const mockedApi = vi.mocked(api, true);

const REASON = 'Plusieurs plaintes de clients vérifiées.';

const artisan: AdminArtisanDetail = {
  id: 'art-1',
  fullName: 'Idrissa Fall',
  phone: '+221771234567',
  bio: null,
  yearsExperience: 8,
  avatarUrl: null,
  isAvailable: true,
  verifiedStatus: 'verified',
  tradeLabels: ['Plomberie'],
  documents: [],
  createdAt: '2026-01-01T10:00:00Z',
  ratingAvg: 4.5,
  reviewCount: 2,
  isSuspended: false,
  suspendedAt: null,
  suspensionReason: null,
  interventions: { en_cours: 1, terminee: 3 },
  history: [],
};

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={['/admin/artisans/art-1']}>
      <Routes>
        <Route path="/admin/artisans/:artisanId" element={<AdminArtisanDetailScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('AdminArtisanDetailScreen', () => {
  it('suspend après confirmation, motif obligatoire, puis montre l’état et l’historique', async () => {
    mockedApi.getAdminArtisan.mockResolvedValue(artisan);
    mockedApi.suspendArtisan.mockResolvedValue({
      ...artisan,
      isSuspended: true,
      suspendedAt: '2026-10-12T10:00:00Z',
      suspensionReason: REASON,
      history: [
        {
          id: 'audit-1',
          createdAt: '2026-10-12T10:00:00Z',
          actorId: 'admin-1',
          actorName: 'Awa Admin',
          action: 'artisan.suspend',
          targetType: 'artisan',
          targetId: 'art-1',
          details: { reason: REASON },
        },
      ],
    });

    renderScreen();
    expect(await screen.findByText('Terminées')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Suspendre' }));
    const dialog = await screen.findByRole('dialog');
    // L'effet exact est dit avant de confirmer.
    expect(
      within(dialog).getByText(/interventions et paiements en cours continuent/),
    ).toBeInTheDocument();
    const confirm = within(dialog).getByRole('button', { name: 'Suspendre l’artisan' });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: REASON } });
    fireEvent.click(confirm);

    await waitFor(() => expect(mockedApi.suspendArtisan).toHaveBeenCalledWith('art-1', REASON));
    expect(await screen.findByRole('button', { name: 'Réactiver' })).toBeInTheDocument();
    expect(screen.getByText('Artisan suspendu')).toBeInTheDocument();
    expect(screen.getAllByText(REASON).length).toBeGreaterThan(0);
  });
});
