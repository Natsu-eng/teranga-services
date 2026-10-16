/**
 * Libellés, étapes et textes de la carte d'intervention (statut, frise
 * d'avancement, dates, clôture). Extraits de `InterventionCard.tsx` sans
 * changement.
 */
import type { StatusTone } from '../../components/ui/StatusPill';
import type { Intervention, InterventionStatus, UserRole } from '../../types';

export const STATUS: Record<InterventionStatus, { label: string; tone: StatusTone }> = {
  proposee: { label: 'En attente de réponse', tone: 'warning' },
  acceptee: { label: 'Acceptée', tone: 'info' },
  en_cours: { label: 'En cours', tone: 'info' },
  terminee: { label: 'Terminée', tone: 'success' },
  annulee: { label: 'Annulée', tone: 'danger' },
  litige: { label: 'Litige', tone: 'danger' },
};

/**
 * Étapes affichées dans la frise d'avancement, et position de chaque
 * statut sur cette frise. Annulée et litige sortent du parcours normal :
 * pas de frise, l'état est expliqué en clair.
 */
export const STEPS = ['Mise en relation', 'Devis', 'Travaux', 'Terminée'] as const;
export const STEP_INDEX: Partial<Record<InterventionStatus, number>> = {
  proposee: 0,
  acceptee: 1,
  en_cours: 2,
  terminee: 3,
};

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** Un litige se décrit : en dessous, il ne serait pas exploitable (même borne que le serveur). */
export const DISPUTE_REASON_MIN_LENGTH = 10;

export function partyLabel(party: UserRole | 'admin'): string {
  if (party === 'client') return 'par le client';
  if (party === 'artisan') return "par l'artisan";
  return 'par Téranga';
}

/** Comment une intervention annulée a été close, du point de vue du lecteur. */
export function cancellationText(intervention: Intervention, role: UserRole): string {
  const cancellation = intervention.cancellation;
  if (!cancellation || cancellation.kind === 'refus') {
    return role === 'client'
      ? "Cette mise en relation a été refusée par l'artisan."
      : 'Vous avez refusé cette mise en relation.';
  }
  if (cancellation.kind === 'arbitrage') {
    return 'Litige tranché par Téranga : le client a été remboursé, aucune commission prélevée.';
  }
  if (cancellation.by === role) return 'Vous avez annulé cette mise en relation.';
  return cancellation.by === 'client'
    ? 'Le client a annulé cette mise en relation.'
    : "L'artisan a annulé cette mise en relation.";
}
