import { createContext } from 'react';
import type { RealtimeEvent, RealtimeStatus } from '../../../lib/realtime/RealtimeConnection';

export type RealtimeListener = (event: RealtimeEvent) => void;

export interface RealtimeContextValue {
  /** Statut du canal temps réel ; tout autre que `open` déclenche le repli REST. */
  status: RealtimeStatus;
  /** S'abonne aux événements (nouveau message, lecture). Renvoie la désinscription. */
  subscribe: (listener: RealtimeListener) => () => void;
  /** Total des messages non lus (badge de navigation) ; `null` hors session. */
  unreadCount: number | null;
  /** Relit le total des non-lus (après un marquage « lu », par exemple). */
  refreshUnread: () => void;
  /**
   * Conversation affichée à l'écran (null : aucune) : pas de notification
   * push pour ses nouveaux messages, déjà visibles en temps réel.
   */
  setViewingConversation: (conversationId: string | null) => void;
}

/**
 * Valeur par défaut (aucun fournisseur monté, ex. tests unitaires d'un
 * écran) : pas de temps réel, donc les écrans restent sur la relecture REST.
 */
export const DEFAULT_REALTIME: RealtimeContextValue = {
  status: 'idle',
  subscribe: () => () => undefined,
  unreadCount: null,
  refreshUnread: () => undefined,
  setViewingConversation: () => undefined,
};

export const RealtimeContext = createContext<RealtimeContextValue>(DEFAULT_REALTIME);
