import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AdminVerificationQueueScreen } from './AdminVerificationQueueScreen';
import { useAuth } from '../auth/hooks/useAuth';
import { api } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { AdminVerificationListItem } from '../../types';

vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listAdminVerifications: vi.fn(),
      getAdminVerificationDocumentBlob: vi.fn(),
      approveVerification: vi.fn(),
      rejectVerification: vi.fn(),
    },
  };
});

const mockedUseAuth = vi.mocked(useAuth);
const mockedApi = vi.mocked(api, true);

function authValue(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    role: 'admin',
    isAuthenticated: true,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

const queueItemFixture: AdminVerificationListItem = {
  id: 'ver-1',
  artisanId: 'artisan-1',
  artisanFullName: 'Idrissa Diop',
  docType: 'cni',
  status: 'pending',
  note: null,
  createdAt: '2026-01-01T10:00:00Z',
  reviewedAt: null,
};

function renderScreen() {
  return render(
    <MemoryRouter>
      <AdminVerificationQueueScreen />
    </MemoryRouter>,
  );
}

describe('AdminVerificationQueueScreen', () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue(authValue({}));
    mockedApi.listAdminVerifications.mockReset().mockResolvedValue([queueItemFixture]);
    mockedApi.getAdminVerificationDocumentBlob
      .mockReset()
      .mockResolvedValue(new Blob(['fake-bytes'], { type: 'image/png' }));
    mockedApi.approveVerification.mockReset();
    mockedApi.rejectVerification.mockReset();
  });

  afterEach(cleanup);

  it('renders the pending queue with the artisan and document info', async () => {
    renderScreen();

    expect(await screen.findByText('Idrissa Diop')).toBeInTheDocument();
    expect(screen.getByText(/Carte d'identité \(CNI\)/)).toBeInTheDocument();
    expect(mockedApi.listAdminVerifications).toHaveBeenCalledWith({ status: 'pending' });
  });

  it('shows a clean empty state when the queue has nothing to review', async () => {
    mockedApi.listAdminVerifications.mockResolvedValue([]);

    renderScreen();

    expect(await screen.findByText('Aucun document en attente de revue.')).toBeInTheDocument();
  });

  it('loads and displays the document preview on demand', async () => {
    renderScreen();

    const showButton = await screen.findByRole('button', { name: 'Afficher le document' });
    fireEvent.click(showButton);

    await waitFor(() =>
      expect(mockedApi.getAdminVerificationDocumentBlob).toHaveBeenCalledWith('ver-1'),
    );
    expect(await screen.findByRole('img')).toBeInTheDocument();
  });

  it('approves the document and removes it from the queue', async () => {
    mockedApi.approveVerification.mockResolvedValue({
      id: 'ver-1',
      docType: 'cni',
      status: 'approved',
      note: null,
      reviewedBy: 'admin-1',
      reviewedAt: '2026-01-02T00:00:00Z',
      artisanId: 'artisan-1',
      artisanVerifiedStatus: 'pending',
    });

    renderScreen();

    const approveButton = await screen.findByRole('button', { name: 'Approuver' });
    fireEvent.click(approveButton);

    await waitFor(() => expect(mockedApi.approveVerification).toHaveBeenCalledWith('ver-1'));
    await waitFor(() =>
      expect(screen.queryByText('Idrissa Diop')).not.toBeInTheDocument(),
    );
  });

  it('requires a motif before the reject can be confirmed', async () => {
    renderScreen();

    const rejectButton = await screen.findByRole('button', { name: 'Rejeter' });
    fireEvent.click(rejectButton);

    const confirmButton = await screen.findByRole('button', { name: 'Confirmer le rejet' });
    expect(confirmButton).toBeDisabled();

    const textarea = screen.getByLabelText(/Motif du rejet/);
    fireEvent.change(textarea, { target: { value: 'ok' } });
    expect(confirmButton).toBeDisabled(); // "ok" fait 2 caractères, sous le minimum de 3

    fireEvent.change(textarea, { target: { value: 'Photo illisible.' } });
    expect(confirmButton).not.toBeDisabled();

    expect(mockedApi.rejectVerification).not.toHaveBeenCalled();
  });

  it('rejects the document with the motif and removes it from the queue', async () => {
    mockedApi.rejectVerification.mockResolvedValue({
      id: 'ver-1',
      docType: 'cni',
      status: 'rejected',
      note: 'Photo illisible.',
      reviewedBy: 'admin-1',
      reviewedAt: '2026-01-02T00:00:00Z',
      artisanId: 'artisan-1',
      artisanVerifiedStatus: 'rejected',
    });

    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: 'Rejeter' }));
    fireEvent.change(screen.getByLabelText(/Motif du rejet/), {
      target: { value: 'Photo illisible.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer le rejet' }));

    await waitFor(() =>
      expect(mockedApi.rejectVerification).toHaveBeenCalledWith('ver-1', 'Photo illisible.'),
    );
    await waitFor(() => expect(screen.queryByText('Idrissa Diop')).not.toBeInTheDocument());
  });

  it('logs out via the header button', async () => {
    const logout = vi.fn();
    mockedUseAuth.mockReturnValue(authValue({ logout }));

    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: /Déconnexion/ }));

    expect(logout).toHaveBeenCalled();
  });
});
