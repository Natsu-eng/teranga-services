import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AdminUsersScreen } from './AdminUsersScreen';
import { ApiError, api } from '../../lib/api';
import type { AdminUser, PageResult } from '../../types/admin';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, listAdminUsers: vi.fn(), grantAdmin: vi.fn(), revokeAdmin: vi.fn() },
  };
});

const mockedApi = vi.mocked(api, true);

function user(overrides: Partial<AdminUser>): AdminUser {
  return {
    id: 'u',
    fullName: 'Compte',
    phone: '+221770000000',
    role: 'client',
    createdAt: '2026-01-01T10:00:00Z',
    hasArtisanProfile: false,
    isSelf: false,
    canGrantAdmin: false,
    canRevokeAdmin: false,
    guard: null,
    ...overrides,
  };
}

function page(items: AdminUser[]): PageResult<AdminUser> {
  return { items, page: 1, total: items.length, totalPages: 1 };
}

const me = user({
  id: 'me',
  fullName: 'Awa Admin',
  role: 'admin',
  isSelf: true,
  guard: 'Vous ne pouvez pas retirer votre propre rôle.',
});
const otherAdmin = user({
  id: 'a2',
  fullName: 'Moussa Admin',
  role: 'admin',
  canRevokeAdmin: true,
});
const client = user({ id: 'c1', fullName: 'Fatou Cliente', canGrantAdmin: true });
const artisan = user({
  id: 'r1',
  fullName: 'Idrissa Artisan',
  role: 'artisan',
  hasArtisanProfile: true,
  guard: 'Compte artisan : un admin utilise un compte dédié.',
});

function renderScreen() {
  return render(
    <MemoryRouter>
      <AdminUsersScreen />
    </MemoryRouter>,
  );
}

function row(name: string): HTMLElement {
  return screen.getByText(name).closest('li') as HTMLElement;
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('AdminUsersScreen', () => {
  it('affiche les garde-fous AVANT toute action et ne propose que les actions permises', async () => {
    mockedApi.listAdminUsers.mockResolvedValue(page([me, otherAdmin, client, artisan]));

    renderScreen();
    await screen.findByText('Awa Admin');

    // Son propre compte : aucun bouton, la raison est écrite.
    expect(within(row('Awa Admin')).queryByRole('button')).not.toBeInTheDocument();
    expect(
      within(row('Awa Admin')).getByText('Vous ne pouvez pas retirer votre propre rôle.'),
    ).toBeInTheDocument();
    // Un compte artisan ne peut pas être promu, et on dit pourquoi.
    expect(within(row('Idrissa Artisan')).queryByRole('button')).not.toBeInTheDocument();
    expect(within(row('Idrissa Artisan')).getByText(/compte dédié/)).toBeInTheDocument();
    expect(
      within(row('Moussa Admin')).getByRole('button', { name: /Retirer le rôle admin/ }),
    ).toBeInTheDocument();
    expect(
      within(row('Fatou Cliente')).getByRole('button', { name: /Accorder le rôle admin/ }),
    ).toBeInTheDocument();
  });

  it('accorde le rôle après confirmation puis recharge la liste', async () => {
    mockedApi.listAdminUsers.mockResolvedValue(page([me, client]));
    mockedApi.grantAdmin.mockResolvedValue({ ...client, role: 'admin', canGrantAdmin: false });

    renderScreen();
    await screen.findByText('Fatou Cliente');
    fireEvent.click(within(row('Fatou Cliente')).getByRole('button'));
    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText(/accède immédiatement à tout le back-office/),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accorder le rôle admin' }));

    await waitFor(() => expect(mockedApi.grantAdmin).toHaveBeenCalledWith('c1', ''));
    await waitFor(() => expect(mockedApi.listAdminUsers).toHaveBeenCalledTimes(2));
  });

  it('montre en clair le refus du serveur (dernier admin), sans rien changer', async () => {
    mockedApi.listAdminUsers.mockResolvedValue(page([me, otherAdmin]));
    mockedApi.revokeAdmin.mockRejectedValue(
      new ApiError(
        'validation',
        'Impossible de retirer le dernier administrateur : promouvez d’abord un autre compte.',
      ),
    );

    renderScreen();
    await screen.findByText('Moussa Admin');
    fireEvent.click(within(row('Moussa Admin')).getByRole('button'));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Retirer le rôle admin' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Impossible de retirer le dernier administrateur',
    );
    expect(mockedApi.listAdminUsers).toHaveBeenCalledTimes(1);
  });
});
