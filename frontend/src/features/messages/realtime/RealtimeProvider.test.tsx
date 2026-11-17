import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { RealtimeProvider } from './RealtimeProvider';
import { useRealtime } from './useRealtime';
import { useAuth } from '../../auth/hooks/useAuth';
import { api } from '../../../lib/api';
import type { AuthContextValue } from '../../auth/auth-context';
import type {
  RealtimeConnection,
  RealtimeConnectionOptions,
  RealtimeEvent,
  RealtimeStatus,
} from '../../../lib/realtime/RealtimeConnection';

vi.mock('../../auth/hooks/useAuth');
vi.mock('../../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/api')>();
  return { ...actual, api: { ...actual.api, getUnreadMessageCount: vi.fn() } };
});

const mockedUseAuth = vi.mocked(useAuth);
const mockedUnread = vi.mocked(api.getUnreadMessageCount);

/** Fausse connexion : enregistre start/stop et permet d'émettre statut et événements. */
class FakeConnection {
  started = 0;
  stopped = 0;
  private statusListener: ((status: RealtimeStatus) => void) | null = null;
  private eventListener: ((event: RealtimeEvent) => void) | null = null;

  constructor(readonly options: RealtimeConnectionOptions) {}

  onStatus(listener: (status: RealtimeStatus) => void) {
    this.statusListener = listener;
    return () => (this.statusListener = null);
  }

  onEvent(listener: (event: RealtimeEvent) => void) {
    this.eventListener = listener;
    return () => (this.eventListener = null);
  }

  viewing: (string | null)[] = [];

  setViewing(conversationId: string | null) {
    this.viewing.push(conversationId);
  }

  start() {
    this.started += 1;
  }

  stop() {
    this.stopped += 1;
  }

  setStatus(status: RealtimeStatus) {
    this.statusListener?.(status);
  }

  emit(event: RealtimeEvent) {
    this.eventListener?.(event);
  }
}

function authValue(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    role: null,
    isAuthenticated: false,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

const client = authValue({
  isAuthenticated: true,
  role: 'client',
  user: {
    id: 'me',
    phone: '+221770000000',
    fullName: 'Awa Diop',
    role: 'client',
    locale: 'fr',
    phoneVerifiedAt: null,
    artisanProfileId: null,
  },
});

function Probe() {
  const realtime = useRealtime();
  return (
    <>
      <p>
        statut={realtime.status} nonlus={String(realtime.unreadCount)}
      </p>
      <button type="button" onClick={() => realtime.setViewingConversation('c1')}>
        ouvrir c1
      </button>
    </>
  );
}

function renderProvider() {
  const connections: FakeConnection[] = [];
  const createConnection = (options: RealtimeConnectionOptions) => {
    const connection = new FakeConnection(options);
    connections.push(connection);
    return connection as unknown as RealtimeConnection;
  };
  const utils = render(
    <RealtimeProvider createConnection={createConnection}>
      <Probe />
    </RealtimeProvider>,
  );
  return { connections, ...utils };
}

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: state });
  document.dispatchEvent(new Event('visibilitychange'));
}

describe('RealtimeProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockedUnread.mockReset().mockResolvedValue(2);
    setVisibility('visible');
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("n'ouvre aucune connexion pour un visiteur", () => {
    mockedUseAuth.mockReturnValue(authValue({}));

    const { connections } = renderProvider();

    expect(connections).toHaveLength(0);
    expect(screen.getByText(/statut=idle nonlus=null/)).toBeInTheDocument();
  });

  it("n'ouvre aucune connexion pour un admin (exclu de la messagerie)", () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'admin' }));

    const { connections } = renderProvider();

    expect(connections).toHaveLength(0);
  });

  it('ouvre une connexion pour un client et lit son compteur de non-lus', async () => {
    mockedUseAuth.mockReturnValue(client);

    const { connections } = renderProvider();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    act(() => connections[0].setStatus('open'));

    expect(connections[0].started).toBe(1);
    expect(connections[0].options.url).toMatch(/\/api\/v1\/realtime\/ws$/);
    expect(screen.getByText(/statut=open nonlus=2/)).toBeInTheDocument();
  });

  it("ferme la connexion quand l'onglet passe en arrière-plan, la rouvre au retour", () => {
    mockedUseAuth.mockReturnValue(client);
    const { connections } = renderProvider();

    act(() => setVisibility('hidden'));
    expect(connections[0].stopped).toBe(1);
    expect(screen.getByText(/statut=idle/)).toBeInTheDocument();

    act(() => setVisibility('visible'));
    expect(connections).toHaveLength(2);
    expect(connections[1].started).toBe(1);
  });

  it("recompte les non-lus quand un message d'autrui arrive, jamais pour les siens", async () => {
    mockedUseAuth.mockReturnValue(client);
    const { connections } = renderProvider();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    mockedUnread.mockClear().mockResolvedValue(5);

    act(() =>
      connections[0].emit({
        type: 'message.created',
        message: {
          id: 'm1',
          conversationId: 'c1',
          seq: 1,
          senderId: 'me',
          body: 'moi',
          contactMasked: false,
          hasAttachment: false,
          attachmentContentType: null,
          createdAt: '2026-10-11T09:00:00Z',
        },
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(mockedUnread).not.toHaveBeenCalled();

    act(() =>
      connections[0].emit({
        type: 'message.created',
        message: {
          id: 'm2',
          conversationId: 'c1',
          seq: 2,
          senderId: 'autre',
          body: 'bonjour',
          contactMasked: false,
          hasAttachment: false,
          attachmentContentType: null,
          createdAt: '2026-10-11T09:01:00Z',
        },
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(mockedUnread).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/nonlus=5/)).toBeInTheDocument();
  });

  it('relit le compteur à intervalle régulier seulement si le temps réel est indisponible', async () => {
    mockedUseAuth.mockReturnValue(client);
    const { connections } = renderProvider();
    act(() => connections[0].setStatus('open'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    mockedUnread.mockClear();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(mockedUnread).not.toHaveBeenCalled();

    act(() => connections[0].setStatus('unavailable'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    mockedUnread.mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_400);
    });
    expect(mockedUnread).toHaveBeenCalled();
  });

  it('transmet le fil à l’écran à la connexion, et le redit à une nouvelle connexion', () => {
    mockedUseAuth.mockReturnValue(client);
    const { connections } = renderProvider();

    act(() => screen.getByRole('button', { name: 'ouvrir c1' }).click());
    expect(connections[0].viewing.at(-1)).toBe('c1');

    // Onglet masqué puis réaffiché : nouvelle connexion, même fil à l'écran.
    act(() => setVisibility('hidden'));
    act(() => setVisibility('visible'));
    expect(connections).toHaveLength(2);
    expect(connections[1].viewing).toEqual(['c1']);
  });
});
