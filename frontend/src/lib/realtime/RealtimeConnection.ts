import type { BackendChatMessage } from '../api/backend-types';
import { mapChatMessage } from '../api/mappers';
import type { ChatMessage } from '../../types';
import {
  REALTIME_CONFIG,
  REALTIME_PROTOCOL,
  TICKET_PROTOCOL_PREFIX,
  type RealtimeConfig,
} from './config';

/**
 * - `idle`        : pas démarrée (visiteur, onglet masqué) ;
 * - `connecting`  : première tentative en cours ;
 * - `open`        : temps réel actif ;
 * - `unavailable` : connexion impossible ou coupée, reconnexion programmée.
 *   Les écrans basculent alors d'eux-mêmes sur la relecture REST (polling).
 */
export type RealtimeStatus = 'idle' | 'connecting' | 'open' | 'unavailable';

export type RealtimeEvent =
  | { type: 'message.created'; message: ChatMessage }
  | { type: 'conversation.read'; conversationId: string; lastReadSeq: number };

/** Le strict nécessaire d'une WebSocket (le vrai `WebSocket` du navigateur convient). */
export interface RealtimeSocket {
  readonly readyState: number;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export interface RealtimeConnectionOptions {
  url: string;
  /** Ticket à usage unique, redemandé à CHAQUE (re)connexion. */
  getTicket: () => Promise<string>;
  createSocket?: (url: string, protocols: string[]) => RealtimeSocket;
  config?: RealtimeConfig;
  /** Aléa du backoff (injectable pour des tests déterministes). */
  random?: () => number;
}

const SOCKET_OPEN = 1;

function parseEvent(raw: unknown): RealtimeEvent | 'ping' | null {
  if (typeof raw !== 'string') return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!data || typeof data !== 'object') return null;
  const event = data as Record<string, unknown>;
  if (event.type === 'ping') return 'ping';
  if (event.type === 'message.created' && event.message && typeof event.message === 'object') {
    return {
      type: 'message.created',
      message: mapChatMessage(event.message as BackendChatMessage),
    };
  }
  if (
    event.type === 'conversation.read' &&
    typeof event.conversation_id === 'string' &&
    typeof event.last_read_seq === 'number'
  ) {
    return {
      type: 'conversation.read',
      conversationId: event.conversation_id,
      lastReadSeq: event.last_read_seq,
    };
  }
  // Type inconnu (version future du protocole) : ignoré sans erreur.
  return null;
}

/**
 * Transport temps réel ISOLÉ du reste de l'application : aucun écran ne
 * manipule de WebSocket. Il gère seul l'authentification par ticket, le
 * délai d'ouverture, la détection d'une connexion morte et la reconnexion
 * avec backoff exponentiel. Les écrans n'en voient que le statut et les
 * événements ; tant que le statut n'est pas `open`, ils relisent l'API REST
 * — l'application reste pleinement fonctionnelle sans WebSocket.
 *
 * Remplacer ce transport (SSE, autre fournisseur) ne toucherait que ce fichier.
 */
export class RealtimeConnection {
  private readonly options: Required<Omit<RealtimeConnectionOptions, 'config'>> & {
    config: RealtimeConfig;
  };
  private socket: RealtimeSocket | null = null;
  private status: RealtimeStatus = 'idle';
  private running = false;
  private attempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private connectTimer: ReturnType<typeof setTimeout> | null = null;
  private watchdogTimer: ReturnType<typeof setTimeout> | null = null;
  /** Conversation à l'écran, renvoyée au serveur à chaque (re)connexion. */
  private viewing: string | null = null;
  private readonly statusListeners = new Set<(status: RealtimeStatus) => void>();
  private readonly eventListeners = new Set<(event: RealtimeEvent) => void>();

  constructor(options: RealtimeConnectionOptions) {
    this.options = {
      url: options.url,
      getTicket: options.getTicket,
      createSocket:
        options.createSocket ??
        ((url, protocols) => new WebSocket(url, protocols) as unknown as RealtimeSocket),
      config: options.config ?? REALTIME_CONFIG,
      random: options.random ?? Math.random,
    };
  }

  getStatus(): RealtimeStatus {
    return this.status;
  }

  onStatus(listener: (status: RealtimeStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  onEvent(listener: (event: RealtimeEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  /**
   * Signale la conversation affichée à l'écran (null : aucune). Le serveur
   * n'envoie alors pas de notification push pour un message de ce fil,
   * déjà visible ici. Mémorisée : renvoyée à chaque (re)connexion.
   */
  setViewing(conversationId: string | null): void {
    if (conversationId === this.viewing) return;
    this.viewing = conversationId;
    this.sendViewing();
  }

  private sendViewing(): void {
    const socket = this.socket;
    if (!socket || socket.readyState !== SOCKET_OPEN) return;
    socket.send(JSON.stringify({ type: 'viewing', conversation_id: this.viewing }));
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.attempts = 0;
    this.setStatus('connecting');
    void this.connect();
  }

  /** Arrêt TOTAL : socket fermée, aucun minuteur ni reconnexion en attente. */
  stop(): void {
    this.running = false;
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      this.detach(socket);
      socket.close(1000, 'arrêt');
    }
    this.setStatus('idle');
  }

  private async connect(): Promise<void> {
    let ticket: string;
    try {
      ticket = await this.options.getTicket();
    } catch {
      this.handleFailure();
      return;
    }
    // Arrêtée pendant l'obtention du ticket : on n'ouvre rien.
    if (!this.running) return;

    let socket: RealtimeSocket;
    try {
      socket = this.options.createSocket(this.options.url, [
        REALTIME_PROTOCOL,
        `${TICKET_PROTOCOL_PREFIX}${ticket}`,
      ]);
    } catch {
      this.handleFailure();
      return;
    }
    this.socket = socket;

    // Une ouverture qui traîne (réseau capricieux, proxy qui bloque) est
    // abandonnée plutôt que d'attendre indéfiniment.
    this.connectTimer = setTimeout(() => {
      if (socket.readyState !== SOCKET_OPEN) socket.close();
    }, this.options.config.connectTimeoutMs);

    socket.onopen = () => {
      this.clearConnectTimer();
      this.attempts = 0;
      this.resetWatchdog();
      // Nouvelle connexion = aucun état côté serveur : on redit le fil ouvert.
      if (this.viewing !== null) this.sendViewing();
      this.setStatus('open');
    };
    socket.onmessage = (event: MessageEvent) => {
      this.resetWatchdog();
      const parsed = parseEvent(event.data);
      if (parsed === 'ping') {
        socket.send(JSON.stringify({ type: 'pong' }));
        return;
      }
      if (parsed) this.eventListeners.forEach((listener) => listener(parsed));
    };
    // Une erreur est toujours suivie d'une fermeture : traitée là.
    socket.onerror = () => undefined;
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.handleFailure();
    };
  }

  private handleFailure(): void {
    this.clearTimers();
    if (!this.running) return;
    this.setStatus('unavailable');
    const { reconnectBaseDelayMs, reconnectMaxDelayMs } = this.options.config;
    const ceiling = Math.min(reconnectMaxDelayMs, reconnectBaseDelayMs * 2 ** this.attempts);
    // Gigue (50 à 100 % du délai) : des milliers de clients coupés en même
    // temps ne se reconnectent pas tous à la même milliseconde.
    const delay = ceiling * (0.5 + this.options.random() * 0.5);
    this.attempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.running) void this.connect();
    }, delay);
  }

  private resetWatchdog(): void {
    if (this.watchdogTimer) clearTimeout(this.watchdogTimer);
    this.watchdogTimer = setTimeout(() => {
      // Plus aucun signe du serveur : connexion morte en silence.
      this.socket?.close();
    }, this.options.config.heartbeatTimeoutMs);
  }

  private clearConnectTimer(): void {
    if (this.connectTimer) clearTimeout(this.connectTimer);
    this.connectTimer = null;
  }

  private clearTimers(): void {
    this.clearConnectTimer();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.watchdogTimer) clearTimeout(this.watchdogTimer);
    this.reconnectTimer = null;
    this.watchdogTimer = null;
  }

  private detach(socket: RealtimeSocket): void {
    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    socket.onerror = null;
  }

  private setStatus(status: RealtimeStatus): void {
    if (status === this.status) return;
    this.status = status;
    this.statusListeners.forEach((listener) => listener(status));
  }
}
