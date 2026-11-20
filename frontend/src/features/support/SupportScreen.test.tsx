import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ApiError, api } from '../../lib/api';
import type { SupportTicket } from '../../types';
import { SupportScreen } from './SupportScreen';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, listMySupportTickets: vi.fn(), createSupportTicket: vi.fn() },
  };
});

const mockedApi = vi.mocked(api, true);
const INTERVENTION_ID = '5f0c2a8e-3d4b-4c1a-9e7f-0a1b2c3d4e5f';
const MESSAGE = 'Je ne retrouve pas le devis de mon artisan.';

function ticket(overrides: Partial<SupportTicket> = {}): SupportTicket {
  return {
    id: 't1',
    category: 'paiement',
    message: 'Mon paiement en espèces n’apparaît pas.',
    interventionId: null,
    interventionTradeLabel: null,
    status: 'ouvert',
    adminReply: null,
    repliedAt: null,
    resolvedAt: null,
    createdAt: '2026-11-10T10:00:00Z',
    ...overrides,
  };
}

function renderScreen(path = '/aide') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/aide" element={<SupportScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

function fillForm(category: string, message: string) {
  fireEvent.change(screen.getByLabelText('Sujet'), { target: { value: category } });
  fireEvent.change(screen.getByLabelText('Votre message'), { target: { value: message } });
}

describe('SupportScreen', () => {
  beforeEach(() => {
    mockedApi.listMySupportTickets.mockReset();
    mockedApi.listMySupportTickets.mockImplementation(async () => []);
    mockedApi.createSupportTicket.mockReset();
  });
  afterEach(cleanup);

  it('affiche les demandes de l’utilisateur et la réponse de Téranga', async () => {
    mockedApi.listMySupportTickets.mockImplementation(async () => [
      ticket({
        status: 'resolu',
        adminReply: 'Paiement retrouvé, tout est en ordre.',
        interventionTradeLabel: 'Plomberie',
      }),
    ]);
    renderScreen();

    const list = await screen.findByRole('list');
    expect(within(list).getByText('Un paiement')).toBeVisible();
    expect(within(list).getByText('Résolue')).toBeVisible();
    expect(within(list).getByText(/Plomberie/)).toBeVisible();
    expect(within(list).getByText('Paiement retrouvé, tout est en ordre.')).toBeVisible();
  });

  it('exige un sujet et un message assez long avant l’envoi', async () => {
    renderScreen();
    const send = await screen.findByRole('button', { name: 'Envoyer' });
    expect(send).toBeDisabled();

    fillForm('compte', 'Court'); // sous le minimum de 10 caractères
    expect(send).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Votre message'), { target: { value: MESSAGE } });
    expect(send).toBeEnabled();
  });

  it('envoie la demande, puis l’ajoute à « Mes demandes »', async () => {
    mockedApi.createSupportTicket.mockImplementation(async () =>
      ticket({ id: 't2', category: 'compte', message: MESSAGE }),
    );
    renderScreen();
    await screen.findByText('Aucune demande pour le moment.');

    fillForm('compte', `  ${MESSAGE}  `);
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));

    await waitFor(() =>
      expect(mockedApi.createSupportTicket).toHaveBeenCalledWith({
        category: 'compte',
        message: MESSAGE,
        interventionId: null,
      }),
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Demande envoyée');
    expect(screen.getByText(MESSAGE)).toBeVisible();
  });

  it('pré-remplit l’intervention venue de la carte, que l’on peut délier', async () => {
    mockedApi.createSupportTicket.mockImplementation(async () => ticket());
    renderScreen(`/aide?intervention=${INTERVENTION_ID}`);

    expect(await screen.findByText(/concerne une de vos interventions/)).toBeVisible();
    fireEvent.change(screen.getByLabelText('Votre message'), { target: { value: MESSAGE } });
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));

    await waitFor(() =>
      expect(mockedApi.createSupportTicket).toHaveBeenCalledWith({
        category: 'utilisateur',
        message: MESSAGE,
        interventionId: INTERVENTION_ID,
      }),
    );
  });

  it('ignore un identifiant d’intervention mal formé dans l’adresse', async () => {
    renderScreen('/aide?intervention=../../admin');

    await screen.findByText('Aucune demande pour le moment.');
    expect(screen.queryByText(/concerne une de vos interventions/)).toBeNull();
  });

  it('affiche le refus du serveur (intervention d’autrui, limite atteinte)', async () => {
    mockedApi.createSupportTicket.mockImplementation(async () => {
      throw new ApiError('not_found', 'Intervention introuvable.');
    });
    renderScreen(`/aide?intervention=${INTERVENTION_ID}`);
    await screen.findByText(/concerne une de vos interventions/);

    fireEvent.change(screen.getByLabelText('Votre message'), { target: { value: MESSAGE } });
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Intervention introuvable.');
  });

  it('dit qui lit le message (l’auteur et l’équipe Téranga seulement)', async () => {
    renderScreen();
    expect(
      await screen.findByText(/Seuls vous et l'équipe Téranga lisez ce message/),
    ).toBeVisible();
  });
});
