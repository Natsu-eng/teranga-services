/**
 * Libellés et formats partagés du back-office. Aucun calcul métier ici :
 * on met en mots ce que le serveur a décidé ou compté.
 */
import type { StatusTone } from '../../components/ui/StatusPill';
import type { ArtisanVerifiedStatus } from '../../types';
import type {
  AccountRole,
  AuditAction,
  AuditTargetType,
  CommissionRateState,
  ReviewModerationStatus,
} from '../../types/admin';

/**
 * Longueur minimale d'un motif (suspension, masquage d'avis), alignée sur
 * la validation serveur, qui reste le seul juge.
 */
export const REASON_MIN_LENGTH = 10;

/** Date et heure courtes (« 12 oct. 2026, 14:05 ») pour le journal et les listes. */
export function formatAdminDateTime(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Date seule (« 12 octobre 2026 »). */
export function formatAdminDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

export const VERIFIED_STATUS: Record<ArtisanVerifiedStatus, { label: string; tone: StatusTone }> = {
  none: { label: 'Profil incomplet', tone: 'neutral' },
  pending: { label: 'À vérifier', tone: 'warning' },
  verified: { label: 'Vérifié', tone: 'success' },
  rejected: { label: 'Refusé', tone: 'danger' },
};

export const ROLE_LABELS: Record<AccountRole, string> = {
  client: 'Client',
  artisan: 'Artisan',
  admin: 'Administrateur',
};

export const REVIEW_STATUS: Record<ReviewModerationStatus, { label: string; tone: StatusTone }> = {
  publie: { label: 'Publié', tone: 'success' },
  signale: { label: 'Signalé', tone: 'warning' },
  masque: { label: 'Masqué', tone: 'neutral' },
};

export const RATE_STATE: Record<CommissionRateState, { label: string; tone: StatusTone }> = {
  en_vigueur: { label: 'En vigueur', tone: 'success' },
  programme: { label: 'Programmé', tone: 'info' },
  archive: { label: 'Archivé', tone: 'neutral' },
};

export const AUDIT_ACTION_LABELS: Record<AuditAction, string> = {
  'admin.bootstrap': 'Premier admin créé (script)',
  'verification.approve': 'Document validé',
  'verification.reject': 'Document refusé',
  'dispute.resolve': 'Litige tranché',
  'artisan.suspend': 'Artisan suspendu',
  'artisan.reactivate': 'Artisan réactivé',
  'user.grant_admin': 'Rôle admin accordé',
  'user.revoke_admin': 'Rôle admin retiré',
  'review.hide': 'Avis masqué',
  'review.restore': 'Avis rétabli',
  'commission_rate.create': 'Taux de commission ajouté',
};

export const AUDIT_TARGET_LABELS: Record<AuditTargetType, string> = {
  verification: 'Document',
  intervention: 'Intervention',
  artisan: 'Artisan',
  user: 'Compte',
  review: 'Avis',
  commission_rate: 'Taux de commission',
};

/** Statuts d'intervention, dans l'ordre du parcours (clés du backend). */
export const INTERVENTION_STATUS_LABELS: Record<string, string> = {
  proposee: 'Proposées',
  acceptee: 'Acceptées',
  en_cours: 'En cours',
  terminee: 'Terminées',
  annulee: 'Annulées',
  litige: 'En litige',
};

/**
 * Pourcentage saisi (« 12,5 » ou « 12.5 ») -> points de base (1250) ;
 * `null` si illisible. Deux décimales au plus : 1 point de base = 0,01 %.
 */
export function percentToBps(input: string): number | null {
  const normalized = input.trim().replace(',', '.');
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  return Math.round(Number(normalized) * 100);
}
