import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RealtimeConnection, type RealtimeEvent, type RealtimeSocket } from './RealtimeConnection';
import type { RealtimeConfig } from './config';
import { resolveRealtimeUrl } from './url';

const CONFIG: RealtimeConfig = {
  threadPollIntervalMs: 5_000,
  listPollIntervalMs: 30_000,
  connectTimeoutMs: 1_000,
  reconnectBaseDelayMs: 100,
  reconnectMaxDelayMs: 800,
  heartbeatTimeoutMs: 5_000,
};

class FakeSocket implements RealtimeSocket {
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(
    readonly url: string,
    readonly protocols: string[],
  ) {}

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.readyState = 3;
    this.onclose?.({} as CloseEvent);
  }

  // Côté « serveur » du test.
  open(): void {
    this.readyState = 1;
    this.onopen?.({} as Event);
  }

  receive(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  drop(): void {
    this.close();
  }
}

function setup(getTicket: () => Promise<string> = async () => 'ticket-1') {
  const sockets: FakeSocket[] = [];
  const connection = new RealtimeConnection({
    url: 'wss://exemple.test/api/v1/realtime/ws',
    getTicket,
    createSocket: (url, protocols) => {
      const socket = new FakeSocket(url, protocols);
      sockets.push(socket);
      return socket;
    },
    config: CONFIG,
    // Backoff déterministe : toujours le plafond du créneau.
    random: () => 1,
  });
  const statuses: string[] = [];
  const events: RealtimeEvent[] = [];
  connection.onStatus((status) => statuses.push(status));
  connection.onEvent((event) => events.push(event));
  return { connection, sockets, statuses, events };
}

describe('RealtimeConnection', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('ouvre la connexion avec la version du protocole et le ticket en sous-protocole', async () => {
    const { connection, sockets, statuses } = setup();

    connection.start();
    await vi.advanceTimersByTimeAsync(0);
    sockets[0].open();

    expect(sockets[0].url).toBe('wss://exemple.test/api/v1/realtime/ws');
    expect(sockets[0].protocols).toEqual(['teranga.v1', 'ticket.ticket-1']);
    expect(statuses).toEqual(['connecting', 'open']);
    connection.stop();
  });

  it('diffuse les messages reçus (au format du front) et répond aux pings', async () => {
    const { connection, sockets, events } = setup();
    connection.start();
    await vi.advanceTimersByTimeAsync(0);
    sockets[0].open();

    sockets[0].receive({ type: 'ping' });
    sockets[0].receive({
      type: 'message.created',
      message: {
        id: 'm1',
        conversation_id: 'c1',
        seq: 7,
        sender_id: 'u1',
        body: 'Bonjour',
        contact_masked: false,
        has_attachment: false,
        attachment_content_type: null,
        created_at: '2026-10-11T10:00:00Z',
      },
    });
    sockets[0].receive({ type: 'conversation.read', conversation_id: 'c1', last_read_seq: 7 });
    sockets[0].receive({ type: 'evenement.futur' });
    sockets[0].onmessage?.({ data: 'pas du json' } as MessageEvent);

    expect(sockets[0].sent).toEqual([JSON.stringify({ type: 'pong' })]);
    expect(events).toEqual([
      {
        type: 'message.created',
        message: expect.objectContaining({ id: 'm1', conversationId: 'c1', seq: 7 }),
      },
      { type: 'conversation.read', conversationId: 'c1', lastReadSeq: 7 },
    ]);
    connection.stop();
  });

  it('passe en indisponible puis se reconnecte avec un backoff exponentiel plafonné', async () => {
    let ticket = 0;
    const { connection, sockets, statuses } = setup(async () => `ticket-${++ticket}`);
    connection.start();
    await vi.advanceTimersByTimeAsync(0);

    sockets[0].drop(); // échec de la 1re tentative
    expect(statuses.at(-1)).toBe('unavailable');
    await vi.advanceTimersByTimeAsync(99);
    expect(sockets).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1); // 100 ms
    expect(sockets).toHaveLength(2);
    // Un NOUVEAU ticket à chaque tentative (usage unique côté serveur).
    expect(sockets[1].protocols[1]).toBe('ticket.ticket-2');

    sockets[1].drop();
    await vi.advanceTimersByTimeAsync(200); // délai doublé
    expect(sockets).toHaveLength(3);

    sockets[2].drop();
    await vi.advanceTimersByTimeAsync(400);
    sockets[3].drop();
    await vi.advanceTimersByTimeAsync(800); // plafond
    sockets[4].drop();
    await vi.advanceTimersByTimeAsync(799);
    expect(sockets).toHaveLength(5);
    await vi.advanceTimersByTimeAsync(1); // toujours plafonné à 800 ms
    expect(sockets).toHaveLength(6);

    // Une ouverture réussie remet le backoff à zéro.
    sockets[5].open();
    expect(statuses.at(-1)).toBe('open');
    sockets[5].drop();
    await vi.advanceTimersByTimeAsync(100);
    expect(sockets).toHaveLength(7);
    connection.stop();
  });

  it('retente si le ticket ne peut pas être obtenu (réseau coupé)', async () => {
    const getTicket = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error('hors ligne'))
      .mockResolvedValue('ticket-ok');
    const { connection, sockets, statuses } = setup(getTicket);

    connection.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(statuses.at(-1)).toBe('unavailable');
    expect(sockets).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(100);
    expect(sockets).toHaveLength(1);
    connection.stop();
  });

  it('abandonne une ouverture qui traîne au-delà du délai', async () => {
    const { connection, sockets, statuses } = setup();
    connection.start();
    await vi.advanceTimersByTimeAsync(0);

    await vi.advanceTimersByTimeAsync(1_000);

    expect(sockets[0].closed).toBe(true);
    expect(statuses.at(-1)).toBe('unavailable');
    connection.stop();
  });

  it('détecte une connexion morte en silence (aucun message du serveur)', async () => {
    const { connection, sockets, statuses } = setup();
    connection.start();
    await vi.advanceTimersByTimeAsync(0);
    sockets[0].open();

    await vi.advanceTimersByTimeAsync(4_999);
    expect(sockets[0].closed).toBe(false);
    await vi.advanceTimersByTimeAsync(1);

    expect(sockets[0].closed).toBe(true);
    expect(statuses.at(-1)).toBe('unavailable');
    connection.stop();
  });

  it('un ping régulier du serveur garde la connexion vivante', async () => {
    const { connection, sockets } = setup();
    connection.start();
    await vi.advanceTimersByTimeAsync(0);
    sockets[0].open();

    for (let i = 0; i < 5; i += 1) {
      await vi.advanceTimersByTimeAsync(4_000);
      sockets[0].receive({ type: 'ping' });
    }

    expect(sockets[0].closed).toBe(false);
    connection.stop();
  });

  it('stop() ferme tout : aucune socket ouverte, aucune reconnexion ensuite', async () => {
    const { connection, sockets, statuses } = setup();
    connection.start();
    await vi.advanceTimersByTimeAsync(0);
    sockets[0].open();

    connection.stop();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(sockets[0].closed).toBe(true);
    expect(sockets).toHaveLength(1);
    expect(statuses.at(-1)).toBe('idle');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('stop() pendant l’obtention du ticket n’ouvre aucune socket', async () => {
    let release: (ticket: string) => void = () => undefined;
    const { connection, sockets } = setup(
      () =>
        new Promise<string>((resolve) => {
          release = resolve;
        }),
    );
    connection.start();
    connection.stop();

    release('ticket-tardif');
    await vi.advanceTimersByTimeAsync(0);

    expect(sockets).toHaveLength(0);
  });
});

describe('resolveRealtimeUrl', () => {
  it('reste sur l’origine courante pour une base relative (wss en https)', () => {
    expect(resolveRealtimeUrl('/api/v1', { protocol: 'https:', host: 'teranga.sn' })).toBe(
      'wss://teranga.sn/api/v1/realtime/ws',
    );
    expect(resolveRealtimeUrl('/api/v1', { protocol: 'http:', host: 'localhost:3000' })).toBe(
      'ws://localhost:3000/api/v1/realtime/ws',
    );
  });

  it('suit l’hôte d’une base absolue', () => {
    expect(
      resolveRealtimeUrl('https://api.teranga.sn/api/v1', {
        protocol: 'https:',
        host: 'teranga.sn',
      }),
    ).toBe('wss://api.teranga.sn/api/v1/realtime/ws');
  });
});
