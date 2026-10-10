import React, { useState } from 'react';
import { Check, ReceiptText } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { TextAreaField, TextField } from '../../components/ui/Field';
import { RatingInput, StarRow } from '../../components/ui/Rating';
import { StatusPill, type StatusTone } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { cn } from '../../lib/cn';
import { formatFcfa } from '../../lib/format';
import type { Intervention, InterventionStatus, UserRole } from '../../types';

const STATUS: Record<InterventionStatus, { label: string; tone: StatusTone }> = {
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
const STEPS = ['Mise en relation', 'Devis', 'Travaux', 'Terminée'] as const;
const STEP_INDEX: Partial<Record<InterventionStatus, number>> = {
  proposee: 0,
  acceptee: 1,
  en_cours: 2,
  terminee: 3,
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** Frise d'avancement : l'étape courante est annoncée aux lecteurs d'écran. */
const ProgressSteps: React.FC<{ current: number }> = ({ current }) => (
  <ol aria-label="Avancement" className="grid grid-cols-4 gap-1.5">
    {STEPS.map((step, index) => {
      const isDone = index < current || (index === current && index === STEPS.length - 1);
      const isCurrent = index === current;
      return (
        <li key={step} className="space-y-1.5" aria-current={isCurrent ? 'step' : undefined}>
          <span
            aria-hidden
            className={cn(
              'block h-1.5 rounded-full',
              isDone || isCurrent ? 'bg-primary-emerald' : 'bg-border-subtle',
            )}
          />
          <span
            className={cn(
              'block text-caption leading-tight',
              isCurrent ? 'font-semibold text-primary' : 'text-muted-foreground',
            )}
          >
            {step}
          </span>
        </li>
      );
    })}
  </ol>
);

interface InterventionCardProps {
  intervention: Intervention;
  role: UserRole;
  onChanged: () => void;
}

/**
 * Carte d'une intervention, partagée par le client (/mes-interventions) et
 * l'artisan (tableau de bord /pro). Même carte des deux côtés ; seules les
 * actions proposées changent selon le rôle — le serveur vérifie chacune.
 */
export const InterventionCard: React.FC<InterventionCardProps> = ({
  intervention,
  role,
  onChanged,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showDeclineForm, setShowDeclineForm] = useState(false);
  const [declineReason, setDeclineReason] = useState('');
  const [laborFcfa, setLaborFcfa] = useState('');
  const [materialsFcfa, setMaterialsFcfa] = useState('');
  const [reviewRating, setReviewRating] = useState(0);
  const [reviewComment, setReviewComment] = useState('');

  const runAction = async (action: () => Promise<unknown>) => {
    setActionError(null);
    setIsSubmitting(true);
    try {
      await action();
      onChanged();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Montants saisis : jamais négatifs ni non numériques ; le total affiché
  // n'est qu'un aperçu, le serveur recalcule le sien.
  const labor = Math.max(0, Number(laborFcfa) || 0);
  const materials = Math.max(0, Number(materialsFcfa) || 0);
  const totalFcfa = labor + materials;
  const status = STATUS[intervention.status];
  const step = STEP_INDEX[intervention.status];
  const { quote } = intervention;

  return (
    <Card as="article" className="space-y-4">
      <div className="space-y-1">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-title font-semibold text-foreground">
            {intervention.serviceRequest.tradeLabel}
          </h3>
          <StatusPill tone={status.tone}>{status.label}</StatusPill>
        </div>
        <p className="text-xs text-muted-foreground">
          Demande du {formatDate(intervention.createdAt)}
        </p>
      </div>

      <p className="text-sm text-muted-foreground line-clamp-3">
        {intervention.serviceRequest.description}
      </p>

      {step !== undefined && <ProgressSteps current={step} />}

      {/* Devis : détail lisible dès qu'il existe, quel que soit l'état. */}
      {quote && (
        <div className="rounded-field bg-emerald-tint p-3 space-y-2">
          <p className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary">
            <ReceiptText aria-hidden className="w-4 h-4" />
            Devis
            {quote.status === 'accepte' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-xs font-semibold text-primary-emerald">
                <Check aria-hidden className="w-3.5 h-3.5" />
                accepté
              </span>
            )}
          </p>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Main d&apos;œuvre</dt>
            <dd className="text-right text-foreground">{formatFcfa(quote.laborFcfa)}</dd>
            <dt className="text-muted-foreground">Matériaux</dt>
            <dd className="text-right text-foreground">{formatFcfa(quote.materialsFcfa)}</dd>
            <dt className="font-semibold text-foreground">Total</dt>
            <dd className="text-right font-display font-semibold text-primary">
              {formatFcfa(quote.totalFcfa)}
            </dd>
          </dl>
        </div>
      )}

      {actionError && (
        <p role="alert" className="text-sm text-destructive">
          {actionError}
        </p>
      )}

      {/* proposee */}
      {intervention.status === 'proposee' &&
        role === 'artisan' &&
        (showDeclineForm ? (
          <div className="space-y-3">
            <TextAreaField
              label="Motif du refus"
              hideLabel
              value={declineReason}
              onChange={(e) => setDeclineReason(e.target.value)}
              placeholder="Motif du refus (optionnel)"
              rows={3}
            />
            <div className="flex gap-2">
              <Button
                variant="danger"
                className="flex-1"
                isLoading={isSubmitting}
                onClick={() =>
                  runAction(() =>
                    api.declineIntervention(intervention.id, declineReason.trim() || null),
                  )
                }
              >
                Confirmer le refus
              </Button>
              <Button
                variant="ghost"
                disabled={isSubmitting}
                onClick={() => setShowDeclineForm(false)}
              >
                Annuler
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button
              variant="brand"
              className="flex-1"
              isLoading={isSubmitting}
              onClick={() => runAction(() => api.acceptIntervention(intervention.id))}
            >
              Accepter
            </Button>
            <Button
              variant="danger-outline"
              className="flex-1"
              disabled={isSubmitting}
              onClick={() => setShowDeclineForm(true)}
            >
              Refuser
            </Button>
          </div>
        ))}
      {intervention.status === 'proposee' && role === 'client' && (
        <p className="text-sm text-muted-foreground">En attente de la réponse de l&apos;artisan.</p>
      )}

      {/* acceptee */}
      {intervention.status === 'acceptee' &&
        (quote && quote.status === 'propose' ? (
          role === 'client' ? (
            <div className="flex gap-2">
              <Button
                variant="primary"
                className="flex-1"
                isLoading={isSubmitting}
                onClick={() => runAction(() => api.acceptQuote(intervention.id))}
              >
                Accepter le devis
              </Button>
              <Button
                variant="danger-outline"
                className="flex-1"
                disabled={isSubmitting}
                onClick={() => runAction(() => api.refuseQuote(intervention.id))}
              >
                Refuser
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Devis envoyé ({formatFcfa(quote.totalFcfa)}), en attente de la réponse du client.
            </p>
          )
        ) : role === 'artisan' ? (
          <div className="space-y-3">
            <p className="text-sm font-semibold text-foreground">Proposer un devis</p>
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="Main d'œuvre"
                type="number"
                inputMode="numeric"
                min={0}
                value={laborFcfa}
                onChange={(e) => setLaborFcfa(e.target.value)}
                placeholder="Main d'œuvre (FCFA)"
              />
              <TextField
                label="Matériaux"
                type="number"
                inputMode="numeric"
                min={0}
                value={materialsFcfa}
                onChange={(e) => setMaterialsFcfa(e.target.value)}
                placeholder="Matériaux (FCFA)"
              />
            </div>
            <p className="text-sm text-muted-foreground" aria-live="polite">
              Total : {formatFcfa(totalFcfa)}
            </p>
            <Button
              variant="brand"
              fullWidth
              isLoading={isSubmitting}
              disabled={totalFcfa <= 0}
              onClick={() =>
                runAction(() =>
                  api.createQuote(intervention.id, { laborFcfa: labor, materialsFcfa: materials }),
                )
              }
            >
              Envoyer le devis
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">En attente du devis de l&apos;artisan.</p>
        ))}

      {/* en_cours */}
      {intervention.status === 'en_cours' && (
        <div className="space-y-3">
          {intervention.agreedAmountFcfa != null && (
            <p className="text-sm text-foreground">
              Montant convenu :{' '}
              <span className="font-semibold">{formatFcfa(intervention.agreedAmountFcfa)}</span>
            </p>
          )}
          {role === 'client' ? (
            <Button
              variant="brand"
              fullWidth
              isLoading={isSubmitting}
              onClick={() => runAction(() => api.completeIntervention(intervention.id))}
            >
              Confirmer la fin des travaux
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">
              En attente de la confirmation du client.
            </p>
          )}
        </div>
      )}

      {/* terminee */}
      {intervention.status === 'terminee' &&
        (intervention.review ? (
          <div className="rounded-field bg-surface-muted p-3 space-y-1">
            <StarRow value={intervention.review.rating} size="md" />
            <p className="text-sm text-muted-foreground">{intervention.review.comment}</p>
          </div>
        ) : role === 'client' ? (
          <div className="space-y-3">
            <p className="text-sm font-semibold text-foreground">Notez l&apos;intervention</p>
            <RatingInput value={reviewRating} onChange={setReviewRating} disabled={isSubmitting} />
            <TextAreaField
              label="Votre avis"
              hideLabel
              value={reviewComment}
              onChange={(e) => setReviewComment(e.target.value)}
              placeholder="Votre avis sur cette intervention..."
              rows={3}
            />
            <Button
              variant="primary"
              fullWidth
              isLoading={isSubmitting}
              disabled={reviewRating === 0 || reviewComment.trim().length === 0}
              onClick={() =>
                runAction(() =>
                  api.createReview(intervention.id, {
                    rating: reviewRating,
                    comment: reviewComment.trim(),
                  }),
                )
              }
            >
              Publier l&apos;avis
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Le client n&apos;a pas encore laissé d&apos;avis.
          </p>
        ))}

      {/* annulee */}
      {intervention.status === 'annulee' && (
        <p className="text-sm text-muted-foreground">
          {role === 'client'
            ? "Cette mise en relation a été refusée par l'artisan."
            : 'Vous avez refusé cette mise en relation.'}
          {intervention.declineReason ? ` Motif : ${intervention.declineReason}` : ''}
        </p>
      )}
    </Card>
  );
};
