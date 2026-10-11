/**
 * Réglages du temps réel de la messagerie, côté navigateur.
 *
 * Le serveur envoie un ping toutes les 25 s (WS_HEARTBEAT_INTERVAL_SECONDS) :
 * sans aucun message reçu pendant `heartbeatTimeoutMs`, la connexion est
 * jugée morte (coupure réseau silencieuse) et rouverte.
 */
export const REALTIME_CONFIG = {
  /** Repli du fil ouvert quand le temps réel est indisponible : relecture `since`. */
  threadPollIntervalMs: 5_000,
  /** Repli de la liste des conversations et du badge de non-lus. */
  listPollIntervalMs: 30_000,
  /** Une connexion qui ne s'ouvre pas dans ce délai est abandonnée (puis retentée). */
  connectTimeoutMs: 8_000,
  /** Reconnexion : délai initial, doublé à chaque échec, plafonné. */
  reconnectBaseDelayMs: 1_000,
  reconnectMaxDelayMs: 30_000,
  /** Sans aucun message du serveur pendant ce délai : connexion morte. */
  heartbeatTimeoutMs: 70_000,
} as const;

export type RealtimeConfig = { readonly [K in keyof typeof REALTIME_CONFIG]: number };

/** Version du protocole, proposée comme sous-protocole WebSocket. */
export const REALTIME_PROTOCOL = 'teranga.v1';
/** Préfixe du sous-protocole qui porte le ticket (jamais l'URL : journaux). */
export const TICKET_PROTOCOL_PREFIX = 'ticket.';
