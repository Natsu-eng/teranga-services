import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import { ArrowLeft, Ban, CheckCircle2 } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { AdminArtisanDetail } from '../../types/admin';
import { formatRadiusKm } from '../artisans/zoneText';
import {
  INTERVENTION_STATUS_LABELS,
  REASON_MIN_LENGTH,
  VERIFIED_STATUS,
  formatAdminDate,
  formatAdminDateTime,
} from './adminText';
import { AuditEntryView } from './components/AuditEntryView';
import { ConfirmActionSheet } from './components/ConfirmActionSheet';

const DOC_LABELS: Record<string, string> = {
  cni: 'Carte d’identité',
  selfie: 'Selfie',
  accreditation: 'Attestation professionnelle',
  address_proof: 'Justificatif de domicile',
};

const DOC_STATUS = {
  pending: { label: 'En attente', tone: 'warning' },
  approved: { label: 'Validé', tone: 'success' },
  rejected: { label: 'Refusé', tone: 'danger' },
} as const;

/**
 * Fiche admin d'un artisan (/admin/artisans/:artisanId) : profil, documents,
 * interventions, décisions passées (journal), et suspension/réactivation —
 * toujours confirmées, motif obligatoire pour suspendre.
 */
export const AdminArtisanDetailScreen: React.FC = () => {
  const { artisanId = '' } = useParams();
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<AdminArtisanDetail>();
  const [action, setAction] = useState<'suspend' | 'reactivate' | null>(null);

  useEffect(() => {
    run(() => api.getAdminArtisan(artisanId));
  }, [run, artisanId]);

  return (
    <div className="space-y-5">
      <Link
        to="/admin/artisans"
        className="inline-flex items-center gap-1 text-sm font-medium text-primary"
      >
        <ArrowLeft aria-hidden className="w-4 h-4" />
        Tous les artisans
      </Link>

      {isLoading && !data ? (
        <Skeleton className="h-72 rounded-card" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data ? (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1 min-w-0">
              <h1 className="font-display text-display-md font-semibold text-primary">
                {data.fullName}
              </h1>
              <p className="text-sm text-muted-foreground">
                {data.phone} · inscrit le {formatAdminDate(data.createdAt)}
              </p>
              <div className="flex flex-wrap gap-2">
                <StatusPill tone={VERIFIED_STATUS[data.verifiedStatus].tone}>
                  {VERIFIED_STATUS[data.verifiedStatus].label}
                </StatusPill>
                {data.isSuspended && <StatusPill tone="danger">Suspendu</StatusPill>}
              </div>
            </div>
            {data.isSuspended ? (
              <Button
                variant="brand"
                leadingIcon={<CheckCircle2 aria-hidden className="w-4 h-4" />}
                onClick={() => setAction('reactivate')}
              >
                Réactiver
              </Button>
            ) : (
              <Button
                variant="danger-outline"
                leadingIcon={<Ban aria-hidden className="w-4 h-4" />}
                onClick={() => setAction('suspend')}
              >
                Suspendre
              </Button>
            )}
          </div>

          {data.isSuspended && (
            <p
              role="status"
              className="rounded-field bg-destructive-soft p-3 text-sm text-foreground"
            >
              Suspendu
              {data.suspendedAt ? ` le ${formatAdminDateTime(data.suspendedAt)}` : ''} :{' '}
              {data.suspensionReason}
            </p>
          )}

          <Card as="section" padding="lg" className="space-y-3" aria-label="Profil">
            <h2 className="font-semibold text-foreground">Profil</h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Métiers</dt>
              <dd className="text-foreground">
                {data.tradeRadii.length > 0
                  ? data.tradeRadii
                      .map((t) => `${t.label} (rayon ${formatRadiusKm(t.radiusM)})`)
                      .join(', ')
                  : 'Aucun'}
              </dd>
              <dt className="text-muted-foreground">Zone</dt>
              <dd
                className={data.zone.placed ? 'text-foreground' : 'font-semibold text-destructive'}
              >
                {!data.zone.placed
                  ? 'Placé nulle part : ne reçoit aucune demande'
                  : data.zone.source === 'neighborhood'
                    ? `Centre de ${data.zone.neighborhoodLabel ?? 'quartier inconnu'}`
                    : 'Position GPS (arrondie)'}
              </dd>
              <dt className="text-muted-foreground">Expérience</dt>
              <dd className="text-foreground">
                {data.yearsExperience !== null ? `${data.yearsExperience} ans` : 'Non renseignée'}
              </dd>
              <dt className="text-muted-foreground">Note</dt>
              <dd className="text-foreground">
                {data.reviewCount > 0 && data.ratingAvg !== null
                  ? `${data.ratingAvg.toFixed(1).replace('.', ',')}/5 (${data.reviewCount} avis)`
                  : 'Aucun avis'}
              </dd>
              <dt className="text-muted-foreground">Disponible</dt>
              <dd className="text-foreground">{data.isAvailable ? 'Oui' : 'Non'}</dd>
            </dl>
            {data.bio && <p className="text-sm text-foreground">{data.bio}</p>}
          </Card>

          <Card as="section" padding="lg" className="space-y-3" aria-label="Interventions">
            <h2 className="font-semibold text-foreground">Interventions</h2>
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1 text-sm">
              {Object.entries(INTERVENTION_STATUS_LABELS).map(([key, label]) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="font-semibold text-foreground">{data.interventions[key] ?? 0}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card as="section" padding="lg" className="space-y-3" aria-label="Documents">
            <h2 className="font-semibold text-foreground">Documents</h2>
            {data.documents.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucun document envoyé.</p>
            ) : (
              <ul className="space-y-2">
                {data.documents.map((doc) => (
                  <li key={doc.id} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm text-foreground">
                      {DOC_LABELS[doc.docType] ?? doc.docType}
                      <span className="text-muted-foreground">
                        {' '}
                        · envoyé le {formatAdminDate(doc.createdAt)}
                      </span>
                      {doc.note && (
                        <span className="block text-muted-foreground">Motif : {doc.note}</span>
                      )}
                    </span>
                    <StatusPill tone={DOC_STATUS[doc.status].tone}>
                      {DOC_STATUS[doc.status].label}
                    </StatusPill>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted-foreground">
              Les documents s’examinent dans{' '}
              <Link to="/admin/verifications" className="font-medium text-primary underline">
                Vérifications
              </Link>
              .
            </p>
          </Card>

          <Card as="section" padding="lg" className="space-y-3" aria-label="Historique">
            <h2 className="font-semibold text-foreground">Historique (décisions et zone)</h2>
            {data.history.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune décision admin pour l’instant.</p>
            ) : (
              <ol className="space-y-4">
                {data.history.map((entry) => (
                  <li key={entry.id}>
                    <AuditEntryView entry={entry} showTarget={false} />
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <ConfirmActionSheet
            open={action === 'suspend'}
            onClose={() => setAction(null)}
            title={`Suspendre ${data.fullName}`}
            tone="danger"
            confirmLabel="Suspendre l’artisan"
            effect={
              <ul className="list-disc pl-5 space-y-1">
                <li>Il disparaît de la recherche et sa fiche publique devient introuvable.</li>
                <li>Il ne peut plus recevoir de nouvelles demandes.</li>
                <li>Ses interventions et paiements en cours continuent normalement.</li>
                <li>Il voit le motif de la suspension. C’est réversible.</li>
              </ul>
            }
            reason={{
              label: 'Motif de la suspension (montré à l’artisan)',
              mode: 'required',
              minLength: REASON_MIN_LENGTH,
            }}
            onConfirm={async (reason) => {
              const updated = await api.suspendArtisan(data.id, reason);
              setData(() => updated);
            }}
          />
          <ConfirmActionSheet
            open={action === 'reactivate'}
            onClose={() => setAction(null)}
            title={`Réactiver ${data.fullName}`}
            confirmLabel="Réactiver l’artisan"
            effect="Il réapparaît dans la recherche et peut de nouveau recevoir des demandes."
            reason={{ label: 'Note', mode: 'optional' }}
            onConfirm={async (note) => {
              const updated = await api.reactivateArtisan(data.id, note);
              setData(() => updated);
            }}
          />
        </>
      ) : null}
    </div>
  );
};
