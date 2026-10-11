import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { MessagesScreen } from './MessagesScreen';
import { useAuth } from '../auth/hooks/useAuth';
import { api, ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { ConversationSummary } from '../../types';

vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, api: { ...actual.api, listConversations: vi.fn() } };
});

const mockedUseAuth = vi.mocked(useAuth);
const mockedList = vi.mocked(api.listConversations);

function authValue(role: 'client' | 'artisan'): AuthContextValue {
  return {
    user: null,
    role,
    isAuthenticated: true,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
  };
}

function summary(overrides: Partial<ConversationSummary>): ConversationSummary {
  return {
    id: 'c1',
    interventionId: 'i1',
    interventionStatus: 'acceptee',
    tradeLabel: 'Plomberie',
    otherParty: {
      userId: 'u2',
      role: 'artisan',
      displayName: 'Idrissa Fall',
      avatarUrl: null,
      artisanProfileId: 'a1',
    },
    lastMessage: {
      body: 'Je passe demain à 10h',
      fromMe: false,
      hasAttachment: false,
      createdAt: '2026-10-11T09:00:00Z',
    },
    unreadCount: 0,
    lastActivityAt: '2026-10-11T09:00:00Z',
    ...overrides,
  };
}

function renderScreen() {
  return render(
    <MemoryRouter>
      <MessagesScreen />
    </MemoryRouter>,
  );
}

describe('MessagesScreen', () => {
  beforeEach(() => {
    mockedUseAuth.mockReturnValue(authValue('client'));
    mockedList.mockReset();
  });
  afterEach(cleanup);

  it("liste les discussions avec l'interlocuteur, l'aperçu et les non-lus", async () => {
    mockedList.mockResolvedValue([
      summary({ unreadCount: 3 }),
      summary({
        id: 'c2',
        otherParty: {
          userId: 'u3',
          role: 'artisan',
          displayName: 'Maty Ndiaye',
          avatarUrl: null,
          artisanProfileId: 'a2',
        },
        lastMessage: {
          body: '',
          fromMe: true,
          hasAttachment: true,
          createdAt: '2026-10-10T09:00:00Z',
        },
      }),
    ]);

    renderScreen();

    const first = await screen.findByRole('link', { name: /Idrissa Fall/ });
    expect(first).toHaveAttribute('href', '/messages/c1');
    expect(within(first).getByText('Je passe demain à 10h')).toBeInTheDocument();
    expect(within(first).getByText('3 messages non lus')).toBeInTheDocument();
    const second = screen.getByRole('link', { name: /Maty Ndiaye/ });
    // Photo envoyée sans légende : « Vous : Photo » (icône décorative).
    expect(within(second).getByText(/Vous :\s*Photo/)).toBeInTheDocument();
  });

  it('rappelle que les coordonnées sont masquées (transparence)', async () => {
    mockedList.mockResolvedValue([]);

    renderScreen();

    expect(await screen.findByText(/masqués automatiquement/)).toBeInTheDocument();
  });

  it('explique à un client comment ouvrir une discussion, avec une action', async () => {
    mockedList.mockResolvedValue([]);

    renderScreen();

    expect(await screen.findByText('Aucune discussion pour le moment.')).toBeInTheDocument();
    expect(screen.getByText(/dès que vous envoyez une demande/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Trouver un artisan' })).toHaveAttribute(
      'href',
      '/recherche',
    );
  });

  it("explique à un artisan d'où viennent les discussions", async () => {
    mockedUseAuth.mockReturnValue(authValue('artisan'));
    mockedList.mockResolvedValue([]);

    renderScreen();

    expect(await screen.findByText(/dès qu'un client vous envoie une demande/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Trouver un artisan' })).not.toBeInTheDocument();
  });

  it('propose de réessayer en cas d’erreur', async () => {
    mockedList
      .mockRejectedValueOnce(new ApiError('network', 'Impossible de contacter le serveur.'))
      .mockResolvedValueOnce([summary({})]);

    renderScreen();

    fireEvent.click(await screen.findByRole('button', { name: 'Réessayer' }));
    expect(await screen.findByRole('link', { name: /Idrissa Fall/ })).toBeInTheDocument();
  });
});
