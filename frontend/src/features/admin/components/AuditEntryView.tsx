import React from 'react';
import type { AuditEntry } from '../../../types/admin';
import { formatRadiusKm } from '../../artisans/zoneText';
import { formatRate } from '../../payments/paymentText';
import { AUDIT_ACTION_LABELS, AUDIT_TARGET_LABELS, formatAdminDateTime } from '../adminText';

/** Libellés des détails connus ; une clé inconnue s'affiche telle quelle. */
const DETAIL_LABELS: Record<string, string> = {
  reason: 'Motif',
  note: 'Note',
  previous_status: 'Statut précédent',
  previous_role: 'Rôle précédent',
  restored_role: 'Rôle rétabli',
  outcome: 'Décision',
  opened_by: 'Litige ouvert par',
  rate_bps: 'Taux',
  trade_code: 'Métier',
  effective_from: 'Début',
  effective_to: 'Fin',
  closed_rate: 'Taux clôturé',
  doc_type: 'Document',
  artisan_verified_status: 'Statut de vérification',
  rating: 'Note de l’avis',
  via: 'Via',
  payout_id: 'Versement',
  artisan_id: 'Artisan',
  // Changement de zone d'intervention (jamais de coordonnées).
  kind: 'Changement',
  counted: 'Compté dans les limites',
  first_placement: 'Premier placement',
  old_source: 'Ancienne source',
  new_source: 'Nouvelle source',
  source: 'Source',
  old_neighborhood_id: 'Ancien quartier',
  new_neighborhood_id: 'Nouveau quartier',
  neighborhood_id: 'Quartier',
  radii: 'Rayons',
  radius_m: 'Rayon',
  old_radius_m: 'Ancien rayon',
  new_radius_m: 'Nouveau rayon',
};

const VALUE_LABELS: Record<string, Record<string, string>> = {
  kind: { position: 'Position', radius: 'Rayon d’un métier' },
  source: { neighborhood: 'Quartier', gps: 'Position GPS (arrondie)' },
  reason: { plafond_migration: 'Rayon ramené au plafond (migration)' },
};
VALUE_LABELS.old_source = VALUE_LABELS.source;
VALUE_LABELS.new_source = VALUE_LABELS.source;

const RADIUS_KEYS = new Set(['radius_m', 'old_radius_m', 'new_radius_m']);

/** Valeur d'un détail, lisible : dates, taux et objets imbriqués compris. */
function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Oui' : 'Non';
  if (typeof value === 'string' && VALUE_LABELS[key]?.[value]) return VALUE_LABELS[key][value];
  if (RADIUS_KEYS.has(key) && typeof value === 'number') return formatRadiusKm(value);
  if (Array.isArray(value)) return value.map((item) => formatValue(key, item)).join(' ; ');
  if (key === 'rate_bps' && typeof value === 'number') return formatRate(value);
  if (key === 'rating' && typeof value === 'number') return `${value}/5`;
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return formatAdminDateTime(value);
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${DETAIL_LABELS[k] ?? k} : ${formatValue(k, v)}`)
      .join(' · ');
  }
  return String(value);
}

interface AuditEntryViewProps {
  entry: AuditEntry;
  /** Masque la ligne « cible » quand le contexte la rend évidente (fiche artisan). */
  showTarget?: boolean;
}

/**
 * Une ligne du journal d'audit : qui, quoi, quand, sur quoi, et TOUS les
 * détails journalisés (rien n'est filtré : transparence).
 */
export const AuditEntryView: React.FC<AuditEntryViewProps> = ({ entry, showTarget = true }) => {
  const details = Object.entries(entry.details);
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <p className="font-medium text-foreground">{AUDIT_ACTION_LABELS[entry.action]}</p>
        <time dateTime={entry.createdAt} className="text-xs text-muted-foreground">
          {formatAdminDateTime(entry.createdAt)}
        </time>
      </div>
      <p className="text-sm text-muted-foreground">
        Par {entry.actorName ?? 'script d’administration (hors application)'}
        {showTarget && (
          <>
            {' · '}
            {AUDIT_TARGET_LABELS[entry.targetType]}
            {entry.targetId && (
              <span className="font-mono text-xs"> {entry.targetId.slice(0, 8)}</span>
            )}
          </>
        )}
      </p>
      {details.length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
          {details.map(([key, value]) => (
            <React.Fragment key={key}>
              <dt className="text-muted-foreground">{DETAIL_LABELS[key] ?? key}</dt>
              <dd className="text-foreground break-words">{formatValue(key, value)}</dd>
            </React.Fragment>
          ))}
        </dl>
      )}
    </div>
  );
};
