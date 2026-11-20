/**
 * Demandes d'aide (« Aide / Signaler un problème ») : un client ou un artisan
 * écrit à Téranga, un admin répond. Le message est toujours la version
 * MASQUÉE par le serveur (numéros, e-mails).
 */

export type SupportCategory = 'compte' | 'utilisateur' | 'paiement' | 'bug' | 'autre';
export type SupportTicketStatus = 'ouvert' | 'resolu';

/** Une demande, vue par son auteur (aucune donnée d'un tiers). */
export interface SupportTicket {
  id: string;
  category: SupportCategory;
  message: string;
  interventionId: string | null;
  /** Métier de l'intervention liée (repère lisible), sinon null. */
  interventionTradeLabel: string | null;
  status: SupportTicketStatus;
  adminReply: string | null;
  repliedAt: string | null;
  resolvedAt: string | null;
  createdAt: string;
}

/** Une demande, vue par un admin : nom public et rôle de l'auteur (jamais son numéro). */
export interface AdminSupportTicket extends SupportTicket {
  authorId: string;
  authorName: string;
  authorRole: 'client' | 'artisan' | 'admin';
}

export interface CreateSupportTicketInput {
  category: SupportCategory;
  message: string;
  /** Intervention concernée (doit appartenir à l'auteur : vérifié par le serveur). */
  interventionId?: string | null;
}

export interface AdminSupportFilters {
  status?: SupportTicketStatus;
  page?: number;
}
