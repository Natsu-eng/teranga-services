import React, { useEffect, useState } from 'react';
import { AlertTriangle, Scale } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Chip } from '../../components/ui/Chip';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { TextAreaField } from '../../components/ui/Field';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { formatFcfa } from '../../lib/format';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { Intervention } from '../../types';
import { adminOutcomeLabels, adminOutcomePill } from '../interventions/disputeText';
import { CHANNEL_LABELS, formatPaymentDate, formatRate } from '../payments/paymentText';

/** Longueur minimale de la justification (alignée sur la validation serveur). */
const MIN_NOTE_LENGTH = 3;

type Outcome = 'libere' | 'rembourse';

const PARTY: Record<string, string> = {
  client: 'le client',
  artisan: "l'artisan",
  admin: 'Téranga',
};

const DisputeCard: React.FC<{ intervention: Intervention; onResolved: (id: string) => void }> = ({
  intervention,
  onResolved,
}) => {
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [note, setNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { dispute, payment } = intervention;
  if (!dispute) return null;
  const isOpen = dispute.outcome === null;
  // Boutons et effets annoncés selon l'argent RÉELLEMENT détenu (séquestre,
  // ou médiation en espèces / hors plateforme) : jamais un remboursement
  // que Téranga ne pourrait pas faire.
  const outcomeLabels = adminOutcomeLabels(payment);

  const confirm = async () => {
    if (!outcome || note.trim().length < MIN_NOTE_LENGTH) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await api.resolveDispute(intervention.id, outcome, note.trim());
      onResolved(intervention.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Décision impossible. Réessayez.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card as="article" padding="lg" className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-foreground">{intervention.serviceRequest.tradeLabel}</p>
          <p className="text-sm text-muted-foreground">
            Signalé par {PARTY[dispute.openedBy]} le {formatPaymentDate(dispute.openedAt)}
          </p>
        </div>
        <StatusPill tone={isOpen ? 'danger' : 'neutral'}>
          {isOpen || dispute.outcome === null
            ? 'À trancher'
            : adminOutcomePill(dispute.outcome, payment)}
        </StatusPill>
      </div>

      <p className="rounded-field bg-destructive-soft p-3 text-sm text-foreground">
        {dispute.reason}
      </p>

      {payment ? (
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">
            Paiement{payment.channel ? ` (${CHANNEL_LABELS[payment.channel]})` : ''}
          </dt>
          <dd className="text-right text-foreground">
            {payment.status === 'retenu'
              ? `${formatFcfa(payment.amountFcfa)} en séquestre`
              : payment.status === null
                ? 'Aucun paiement'
                : formatFcfa(payment.amountFcfa)}
          </dd>
          <dt className="text-muted-foreground">
            Commission ({formatRate(payment.commission.rateBps)})
          </dt>
          <dd className="text-right text-foreground">
            {formatFcfa(payment.commission.amountFcfa)}
          </dd>
          <dt className="font-semibold text-foreground">Net artisan</dt>
          <dd className="text-right font-semibold text-foreground">
            {formatFcfa(payment.netFcfa)}
          </dd>
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">Aucun devis accepté.</p>
      )}

      {!isOpen && dispute.resolutionNote && (
        <p className="text-sm text-muted-foreground">Décision : {dispute.resolutionNote}</p>
      )}

      {isOpen &&
        (outcome ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">
              <span className="font-semibold">{outcomeLabels[outcome].action}.</span>{' '}
              {outcomeLabels[outcome].effect}
            </p>
            <TextAreaField
              label="Justification (visible des deux parties)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
            />
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                variant={outcome === 'libere' ? 'brand' : 'danger'}
                className="flex-1"
                isLoading={isSubmitting}
                disabled={note.trim().length < MIN_NOTE_LENGTH}
                onClick={confirm}
              >
                Confirmer la décision
              </Button>
              <Button variant="ghost" disabled={isSubmitting} onClick={() => setOutcome(null)}>
                Retour
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button variant="brand" size="sm" onClick={() => setOutcome('libere')}>
              {outcomeLabels.libere.action}
            </Button>
            <Button variant="danger-outline" size="sm" onClick={() => setOutcome('rembourse')}>
              {outcomeLabels.rembourse.action}
            </Button>
          </div>
        ))}
    </Card>
  );
};

/**
 * Litiges (/admin/litiges) : un admin examine (motif, échanges, montants)
 * puis tranche, toujours justifié. Paiement en ligne retenu : versement à
 * l'artisan ou remboursement du client. Espèces ou hors plateforme : Téranga
 * ne détient rien, la décision clôt la médiation (commission due ou annulée).
 */
export const AdminDisputesScreen: React.FC = () => {
  const [resolved, setResolved] = useState(false);
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<Intervention[]>();

  useEffect(() => {
    run(() => api.listAdminDisputes({ resolved }));
  }, [run, resolved]);

  const removeResolved = (id: string) =>
    setData((prev) => (prev ? prev.filter((item) => item.id !== id) : prev));

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-display-md font-semibold text-primary">Litiges</h1>
        <p className="text-sm text-muted-foreground">
          Un paiement en ligne retenu reste gelé jusqu&apos;à votre décision. En espèces, Téranga ne
          détient pas l&apos;argent : la décision clôt la médiation.
        </p>
      </div>
      <div className="flex gap-2" role="group" aria-label="Filtrer les litiges">
        <Chip selected={!resolved} onClick={() => setResolved(false)}>
          À trancher
        </Chip>
        <Chip selected={resolved} onClick={() => setResolved(true)}>
          Tranchés
        </Chip>
      </div>

      {isLoading && !data ? (
        <div className="space-y-4" aria-busy="true">
          <Skeleton className="h-52 rounded-card" />
        </div>
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data && data.length === 0 ? (
        <EmptyState
          icon={resolved ? <Scale /> : <AlertTriangle />}
          title={resolved ? 'Aucun litige tranché.' : 'Aucun litige à trancher.'}
        />
      ) : (
        <ul className="space-y-4">
          {(data ?? []).map((intervention) => (
            <li key={intervention.id}>
              <DisputeCard intervention={intervention} onResolved={removeResolved} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
