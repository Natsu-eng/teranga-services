import type { StatusTone } from '../../components/ui/StatusPill';
import type { SupportCategory, SupportTicketStatus } from '../../types';

/** Bornes du message (mêmes valeurs que le serveur, `app/models/support.py`). */
export const SUPPORT_MESSAGE_MIN_LENGTH = 10;
export const SUPPORT_MESSAGE_MAX_LENGTH = 2000;
/** Réponse d'un admin (mêmes bornes que le serveur). */
export const SUPPORT_REPLY_MIN_LENGTH = 3;

/** Sujets proposés, dans l'ordre d'affichage. */
export const SUPPORT_CATEGORIES: { value: SupportCategory; label: string }[] = [
  { value: 'compte', label: 'Mon compte' },
  { value: 'utilisateur', label: 'Un artisan ou un client' },
  { value: 'paiement', label: 'Un paiement' },
  { value: 'bug', label: "Un problème dans l'application" },
  { value: 'autre', label: 'Autre chose' },
];

export const SUPPORT_CATEGORY_LABELS: Record<SupportCategory, string> = Object.fromEntries(
  SUPPORT_CATEGORIES.map(({ value, label }) => [value, label]),
) as Record<SupportCategory, string>;

export const SUPPORT_STATUS: Record<SupportTicketStatus, { label: string; tone: StatusTone }> = {
  ouvert: { label: 'En cours', tone: 'warning' },
  resolu: { label: 'Résolue', tone: 'success' },
};

/** Identifiant d'intervention reçu dans l'URL : accepté seulement s'il a la forme d'un UUID. */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function interventionIdFromQuery(value: string | null): string | null {
  return value && UUID_RE.test(value) ? value : null;
}
