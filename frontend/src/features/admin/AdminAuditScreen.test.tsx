import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AdminAuditScreen } from './AdminAuditScreen';
import { api } from '../../lib/api';
import type { AuditEntry, PageResult } from '../../types/admin';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, api: { ...actual.api, listAuditEntries: vi.fn() } };
});

const mockedApi = vi.mocked(api, true);

const bootstrap: AuditEntry = {
  id: 'audit-1',
  createdAt: '2026-10-01T09:00:00Z',
  actorId: null,
  actorName: null,
  action: 'admin.bootstrap',
  targetType: 'user',
  targetId: 'user-1',
  details: { previous_role: 'client', via: 'scripts/create_admin.py' },
};

function page(items: AuditEntry[]): PageResult<AuditEntry> {
  return { items, page: 1, total: items.length, totalPages: 1 };
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe('AdminAuditScreen', () => {
  it('affiche chaque entrée avec tous ses détails, en lecture seule', async () => {
    mockedApi.listAuditEntries.mockResolvedValue(page([bootstrap]));

    render(
      <MemoryRouter>
        <AdminAuditScreen />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Premier admin créé (script)')).toBeInTheDocument();
    expect(screen.getByText(/script d’administration/)).toBeInTheDocument();
    expect(screen.getByText('scripts/create_admin.py')).toBeInTheDocument();
    // Aucune action d'édition ou de suppression n'est proposée.
    expect(screen.queryByRole('button', { name: /Supprimer|Modifier/ })).not.toBeInTheDocument();
  });

  it('filtre par action côté serveur', async () => {
    mockedApi.listAuditEntries.mockResolvedValue(page([]));

    render(
      <MemoryRouter>
        <AdminAuditScreen />
      </MemoryRouter>,
    );
    await screen.findByText('Journal vide.');
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'user.revoke_admin' } });

    await waitFor(() =>
      expect(mockedApi.listAuditEntries).toHaveBeenLastCalledWith({
        action: 'user.revoke_admin',
        targetType: undefined,
        page: 1,
      }),
    );
  });
});
