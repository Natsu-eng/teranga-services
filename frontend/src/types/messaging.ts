/**
 * Messagerie in-app.
 */
import type { InterventionStatus } from './interventions';

/* ------------------------------------------------------------------ Messagerie */

/**
 * Message d'un fil, identique pour les deux participants (REST et temps
 * réel). `body` est TOUJOURS la version masquée par le serveur ;
 * `contactMasked` signale qu'un numéro ou un e-mail a été retiré, pour
 * l'avertissement de transparence.
 */
export interface ChatMessage {
  id: string;
  conversationId: string;
  /** Ordre strictement croissant attribué par le serveur (curseur `since`). */
  seq: number;
  senderId: string;
  body: string;
  contactMasked: boolean;
  /** Image jointe : jamais d'URL publique, contenu lu par un appel authentifié. */
  hasAttachment: boolean;
  attachmentContentType: string | null;
  createdAt: string;
}

export interface ConversationParticipant {
  userId: string;
  role: 'client' | 'artisan';
  /** Nom public (jamais un numéro de téléphone). */
  displayName: string;
  avatarUrl: string | null;
  /** Fiche publique de l'artisan ; `null` pour un client. */
  artisanProfileId: string | null;
}

export interface ConversationSummary {
  id: string;
  interventionId: string | null;
  interventionStatus: InterventionStatus | null;
  tradeLabel: string | null;
  otherParty: ConversationParticipant;
  lastMessage: {
    body: string;
    fromMe: boolean;
    hasAttachment: boolean;
    createdAt: string;
  } | null;
  unreadCount: number;
  lastActivityAt: string;
}

export interface ConversationDetail {
  id: string;
  interventionId: string | null;
  interventionStatus: InterventionStatus | null;
  tradeLabel: string | null;
  otherParty: ConversationParticipant;
  /** Dernier message vu par l'utilisateur courant (séparateur « nouveaux »). */
  myLastReadSeq: number;
  /** Faux si la mise en relation a été refusée : fil en lecture seule. */
  canSend: boolean;
  createdAt: string;
}

/** Page d'historique, toujours du plus ancien au plus récent. */
export interface MessageHistory {
  items: ChatMessage[];
  /** Des messages plus anciens existent (remontée dans l'historique). */
  hasMore: boolean;
}
