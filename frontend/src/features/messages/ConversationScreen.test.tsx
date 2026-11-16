import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ConversationScreen } from './ConversationScreen';
import {
  RealtimeContext,
  type RealtimeContextValue,
  type RealtimeListener,
} from './realtime/realtime-context';
import { useAuth } from '../auth/hooks/useAuth';
import { api, ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { ChatMessage, ConversationDetail } from '../../types';
import type { RealtimeStatus } from '../../lib/realtime/RealtimeConnection';

vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getConversation: vi.fn(),
      listMessages: vi.fn(),
      sendMessage: vi.fn(),
      sendImageMessage: vi.fn(),
      markConversationRead: vi.fn(),
      getMessageAttachmentBlob: vi.fn(),
    },
  };
});

const mockedUseAuth = vi.mocked(useAuth);
const mockedApi = vi.mocked(api);

const ME = 'client-1';
const ARTISAN = 'artisan-1';

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: 'm1',
    conversationId: 'c1',
    seq: 1,
    senderId: ARTISAN,
    body: 'Bonjour, je peux passer demain.',
    contactMasked: false,
    hasAttachment: false,
    attachmentContentType: null,
    createdAt: '2026-10-11T09:00:00Z',
    ...overrides,
  };
}

const conversationFixture: ConversationDetail = {
  id: 'c1',
  interventionId: 'i1',
  interventionStatus: 'acceptee',
  tradeLabel: 'Plomberie',
  otherParty: {
    userId: ARTISAN,
    role: 'artisan',
    displayName: 'Idrissa Fall',
    avatarUrl: null,
    artisanProfileId: 'a1',
  },
  myLastReadSeq: 0,
  canSend: true,
  createdAt: '2026-10-11T08:00:00Z',
};

function authValue(): AuthContextValue {
  return {
    user: {
      id: ME,
      phone: '+221770000000',
      fullName: 'Awa Diop',
      role: 'client',
      locale: 'fr',
      phoneVerifiedAt: '2026-01-01T00:00:00Z',
      artisanProfileId: null,
    },
    role: 'client',
    isAuthenticated: true,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
  };
}

/** Faux canal temps réel, contrôlé par le test (statut + émission d'événements). */
function fakeRealtime(status: RealtimeStatus) {
  const listeners = new Set<RealtimeListener>();
  const value: RealtimeContextValue = {
    status,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    unreadCount: 0,
    refreshUnread: vi.fn(),
    setViewingConversation: vi.fn(),
  };
  return {
    value,
    emit: (event: Parameters<RealtimeListener>[0]) => listeners.forEach((l) => l(event)),
  };
}

function renderThread(realtime: RealtimeContextValue) {
  return render(
    <RealtimeContext.Provider value={realtime}>
      <MemoryRouter initialEntries={['/messages/c1']}>
        <Routes>
          <Route path="/messages/:conversationId" element={<ConversationScreen />} />
        </Routes>
      </MemoryRouter>
    </RealtimeContext.Provider>,
  );
}

function messageList() {
  return screen.getByRole('list', { name: 'Messages' });
}

describe('ConversationScreen', () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue(authValue());
    mockedApi.getConversation.mockReset().mockResolvedValue(conversationFixture);
    mockedApi.listMessages.mockReset().mockResolvedValue({ items: [message({})], hasMore: false });
    mockedApi.sendMessage.mockReset();
    mockedApi.markConversationRead.mockReset().mockResolvedValue(conversationFixture);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("affiche l'interlocuteur, son métier et l'historique", async () => {
    renderThread(fakeRealtime('open').value);

    expect(await screen.findByRole('heading', { name: 'Idrissa Fall' })).toBeInTheDocument();
    expect(screen.getByText('Plomberie')).toBeInTheDocument();
    expect(within(messageList()).getByText('Bonjour, je peux passer demain.')).toBeInTheDocument();
  });

  it('signale le fil à l’écran, puis plus aucun en le quittant', async () => {
    const realtime = fakeRealtime('open').value;
    const { unmount } = renderThread(realtime);
    await screen.findByRole('heading', { name: 'Idrissa Fall' });

    expect(realtime.setViewingConversation).toHaveBeenLastCalledWith('c1');
    unmount();
    expect(realtime.setViewingConversation).toHaveBeenLastCalledWith(null);
  });

  it('avertit avec transparence quand des coordonnées ont été masquées', async () => {
    mockedApi.listMessages.mockResolvedValue({
      items: [message({ body: 'Appelez le [numéro masqué]', contactMasked: true })],
      hasMore: false,
    });

    renderThread(fakeRealtime('open').value);

    expect(await screen.findByText('Appelez le [numéro masqué]')).toBeInTheDocument();
    expect(
      screen.getByText(/Des coordonnées ont été masquées dans ce message/),
    ).toBeInTheDocument();
  });

  it('affiche le message aussitôt (optimiste) puis le confirme avec la version du serveur', async () => {
    let confirm: (value: ChatMessage) => void = () => undefined;
    mockedApi.sendMessage.mockReturnValue(
      new Promise<ChatMessage>((resolve) => {
        confirm = resolve;
      }),
    );
    renderThread(fakeRealtime('open').value);
    await screen.findByText('Bonjour, je peux passer demain.');

    fireEvent.change(screen.getByLabelText('Votre message'), {
      target: { value: 'Mon numéro : 77 123 45 67' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));

    // Visible tout de suite, en cours d'envoi.
    expect(screen.getByText('Mon numéro : 77 123 45 67')).toBeInTheDocument();
    expect(screen.getByText('Envoi…')).toBeInTheDocument();
    expect(mockedApi.sendMessage).toHaveBeenCalledWith('c1', 'Mon numéro : 77 123 45 67');

    await act(async () => {
      confirm(
        message({
          id: 'm2',
          seq: 2,
          senderId: ME,
          body: 'Mon numéro : [numéro masqué]',
          contactMasked: true,
        }),
      );
    });

    // Remplacé par le message enregistré (masqué), avec l'avertissement.
    expect(screen.queryByText('Envoi…')).not.toBeInTheDocument();
    expect(screen.queryByText('Mon numéro : 77 123 45 67')).not.toBeInTheDocument();
    expect(screen.getByText('Mon numéro : [numéro masqué]')).toBeInTheDocument();
    expect(screen.getByText(/Vos coordonnées ont été masquées/)).toBeInTheDocument();
  });

  it('garde le message en échec avec la raison, puis le renvoie sur « Réessayer »', async () => {
    mockedApi.sendMessage
      .mockRejectedValueOnce(new ApiError('network', 'Impossible de contacter le serveur.'))
      .mockResolvedValueOnce(message({ id: 'm2', seq: 2, senderId: ME, body: 'Je confirme' }));
    renderThread(fakeRealtime('open').value);
    await screen.findByText('Bonjour, je peux passer demain.');

    fireEvent.change(screen.getByLabelText('Votre message'), { target: { value: 'Je confirme' } });
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Impossible de contacter le serveur.',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(mockedApi.sendMessage).toHaveBeenCalledTimes(2);
    expect(within(messageList()).getByText('Je confirme')).toBeInTheDocument();
  });

  it("n'affiche qu'une fois un message reçu à la fois par le temps réel et par REST", async () => {
    const realtime = fakeRealtime('open');
    const confirmed = message({ id: 'm2', seq: 2, senderId: ME, body: 'Une seule fois' });
    mockedApi.sendMessage.mockImplementation(async () => {
      // Le temps réel livre le message AVANT la réponse REST.
      realtime.emit({ type: 'message.created', message: confirmed });
      return confirmed;
    });
    renderThread(realtime.value);
    await screen.findByText('Bonjour, je peux passer demain.');

    fireEvent.change(screen.getByLabelText('Votre message'), {
      target: { value: 'Une seule fois' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));

    await waitFor(() => expect(screen.queryByText('Envoi…')).not.toBeInTheDocument());
    expect(within(messageList()).getAllByText('Une seule fois')).toHaveLength(1);
  });

  it('ajoute en direct un message diffusé par le temps réel', async () => {
    const realtime = fakeRealtime('open');
    renderThread(realtime.value);
    await screen.findByText('Bonjour, je peux passer demain.');

    act(() => {
      realtime.emit({
        type: 'message.created',
        message: message({ id: 'm9', seq: 9, body: 'Je suis devant chez vous' }),
      });
    });

    expect(screen.getByText('Je suis devant chez vous')).toBeInTheDocument();
  });

  it("ignore un message d'une autre conversation", async () => {
    const realtime = fakeRealtime('open');
    renderThread(realtime.value);
    await screen.findByText('Bonjour, je peux passer demain.');

    act(() => {
      realtime.emit({
        type: 'message.created',
        message: message({ id: 'x', conversationId: 'autre', seq: 50, body: 'Fil voisin' }),
      });
    });

    expect(screen.queryByText('Fil voisin')).not.toBeInTheDocument();
  });

  describe('repli automatique sur la relecture REST', () => {
    it('relit les nouveaux messages (since) tant que le temps réel est indisponible', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      renderThread(fakeRealtime('unavailable').value);
      await screen.findByText('Bonjour, je peux passer demain.');
      // Indicateur discret, jamais alarmant.
      expect(screen.getByRole('status')).toHaveTextContent(/quelques secondes de délai/);

      mockedApi.listMessages.mockResolvedValue({
        items: [message({ id: 'm2', seq: 2, body: 'Arrivé pendant la coupure' })],
        hasMore: false,
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
      });

      expect(mockedApi.listMessages).toHaveBeenCalledWith('c1', { since: 1, limit: 100 });
      expect(screen.getByText('Arrivé pendant la coupure')).toBeInTheDocument();
    });

    it('envoie et confirme un message par REST sans aucun temps réel', async () => {
      // Preuve de fiabilité : l'envoi ne dépend jamais du WebSocket.
      mockedApi.sendMessage.mockResolvedValue(
        message({ id: 'm2', seq: 2, senderId: ME, body: 'Envoyé sans WebSocket' }),
      );
      renderThread(fakeRealtime('unavailable').value);
      await screen.findByText('Bonjour, je peux passer demain.');

      fireEvent.change(screen.getByLabelText('Votre message'), {
        target: { value: 'Envoyé sans WebSocket' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Envoyer' }));

      expect(mockedApi.sendMessage).toHaveBeenCalledWith('c1', 'Envoyé sans WebSocket');
      await waitFor(() => expect(screen.queryByText('Envoi…')).not.toBeInTheDocument());
      expect(within(messageList()).getAllByText('Envoyé sans WebSocket')).toHaveLength(1);
    });

    it('ne relit plus à intervalle régulier quand le temps réel est ouvert', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      renderThread(fakeRealtime('open').value);
      await screen.findByText('Bonjour, je peux passer demain.');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      const callsAfterCatchUp = mockedApi.listMessages.mock.calls.length;

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });

      expect(mockedApi.listMessages.mock.calls.length).toBe(callsAfterCatchUp);
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });
  });

  it('marque la conversation lue quand un message de l’autre partie est affiché', async () => {
    const realtime = fakeRealtime('open');
    renderThread(realtime.value);
    await screen.findByText('Bonjour, je peux passer demain.');

    await waitFor(() => expect(mockedApi.markConversationRead).toHaveBeenCalledWith('c1', 1));
    await waitFor(() => expect(realtime.value.refreshUnread).toHaveBeenCalled());
  });

  it('affiche un écran neutre pour un fil inaccessible (403), sans indice', async () => {
    mockedApi.getConversation.mockRejectedValue(
      new ApiError('forbidden', "Vous n'avez pas accès à cette conversation."),
    );

    renderThread(fakeRealtime('open').value);

    expect(await screen.findByText('Cette discussion est introuvable.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Votre message')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Mes messages' })).toHaveAttribute('href', '/messages');
  });

  it('passe en lecture seule quand la mise en relation a été refusée', async () => {
    mockedApi.getConversation.mockResolvedValue({ ...conversationFixture, canSend: false });

    renderThread(fakeRealtime('open').value);

    expect(await screen.findByText(/lecture seule/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Votre message')).not.toBeInTheDocument();
  });
});
