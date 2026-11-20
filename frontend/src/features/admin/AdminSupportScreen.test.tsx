import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ApiError, api } from '../../lib/api';
import type { AdminSupportTicket } from '../../types';
import type { PageResult } from '../../types/admin';
import { AdminSupportScreen } from './AdminSupportScreen';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, listAdminSupportTickets: vi.fn(), replySupportTicket: vi.fn() },
  };
});

const mockedApi = vi.mocked(api, true);

const open: AdminSupportTicket = {
  id: 't1',
  category: 'paiement',
  message: 'Rappelez-moi au 77 123 45 67, mon paiement n’apparaît pas.',
  interventionId: null,
  interventionTradeLabel: null,
  status: 'ouvert',
  adminReply: null,
  repliedAt: null,
  resolvedAt: null,
  createdAt: '2026-11-10T10:00:00Z',
  authorId: 'u1',
  authorName: 'Awa Diop',
  authorRole: 'client',
};

function page(items: AdminSupportTicket[]): PageResult<AdminSupportTicket> {
  return { items, page: 1, total: items.length, totalPages: 1 };
}

function renderScreen() {
  return render(
    <MemoryRouter>
      <AdminSupportScreen />
    </MemoryRouter>,
  );
}

describe('AdminSupportScreen', () => {
  beforeEach(() => {
    mockedApi.listAdminSupportTickets.mockReset();
    mockedApi.listAdminSupportTickets.mockImplementation(async () => page([open]));
    mockedApi.replySupportTicket.mockReset();
  });
  afterEach(cleanup);

  it('présente la demande : sujet, auteur, message tel qu’écrit', async () => {
    renderScreen();

    expect(await screen.findByText('Un paiement')).toBeVisible();
    expect(screen.getByText(/Client · Awa Diop/)).toBeVisible();
    expect(screen.getByText(/Rappelez-moi au 77 123 45 67/)).toBeVisible();
    expect(mockedApi.listAdminSupportTickets).toHaveBeenCalledWith({ status: 'ouvert', page: 1 });
  });

  it('répond et clôt : la demande quitte la file des ouvertes', async () => {
    mockedApi.replySupportTicket.mockImplementation(async () => ({
      ...open,
      status: 'resolu',
      adminReply: 'Paiement retrouvé.',
      resolvedAt: '2026-11-11T10:00:00Z',
    }));
    renderScreen();

    fireEvent.change(await screen.findByLabelText("Réponse (visible de l'auteur)"), {
      target: { value: 'Paiement retrouvé.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Répondre et clore' }));

    await waitFor(() =>
      expect(mockedApi.replySupportTicket).toHaveBeenCalledWith('t1', 'Paiement retrouvé.', true),
    );
    expect(await screen.findByText('Aucune demande en attente.')).toBeVisible();
  });

  it('une réponse d’attente laisse la demande ouverte, réponse visible', async () => {
    mockedApi.replySupportTicket.mockImplementation(async () => ({
      ...open,
      adminReply: 'Pouvez-vous préciser la date ?',
      repliedAt: '2026-11-11T10:00:00Z',
    }));
    renderScreen();

    fireEvent.change(await screen.findByLabelText("Réponse (visible de l'auteur)"), {
      target: { value: 'Pouvez-vous préciser la date ?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Répondre sans clore' }));

    await waitFor(() =>
      expect(mockedApi.replySupportTicket).toHaveBeenCalledWith(
        't1',
        'Pouvez-vous préciser la date ?',
        false,
      ),
    );
    expect(await screen.findByText('Pouvez-vous préciser la date ?')).toBeVisible();
  });

  it('affiche le refus du serveur', async () => {
    mockedApi.replySupportTicket.mockImplementation(async () => {
      throw new ApiError('validation', 'Cette demande est déjà résolue.');
    });
    renderScreen();

    fireEvent.change(await screen.findByLabelText("Réponse (visible de l'auteur)"), {
      target: { value: 'Réponse.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Répondre et clore' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('déjà résolue');
  });

  it('filtre les demandes résolues', async () => {
    renderScreen();
    await screen.findByText('Un paiement');

    fireEvent.click(screen.getByRole('button', { name: 'Résolues' }));

    await waitFor(() =>
      expect(mockedApi.listAdminSupportTickets).toHaveBeenLastCalledWith({
        status: 'resolu',
        page: 1,
      }),
    );
  });
});
