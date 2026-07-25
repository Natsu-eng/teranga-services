import React, { useState } from 'react';
import { Star } from 'lucide-react';
import { ApiError, api } from '../../lib/api';
import { formatFcfa } from '../../lib/format';
import type { Intervention, InterventionStatus, UserRole } from '../../types';

const STATUS_LABELS: Record<InterventionStatus, string> = {
  proposee: 'En attente de réponse',
  acceptee: 'Acceptée',
  en_cours: 'En cours',
  terminee: 'Terminée',
  annulee: 'Annulée',
  litige: 'Litige',
};

const STATUS_STYLES: Record<InterventionStatus, string> = {
  proposee: 'bg-accent-soft/50 text-accent-foreground',
  en_cours: 'bg-primary-emerald/10 text-primary',
  acceptee: 'bg-primary-emerald/10 text-primary',
  terminee: 'bg-success/10 text-success',
  annulee: 'bg-destructive-soft/30 text-destructive',
  litige: 'bg-destructive-soft/30 text-destructive',
};

interface InterventionCardProps {
  intervention: Intervention;
  role: UserRole;
  onChanged: () => void;
}

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

  const totalFcfa = (Number(laborFcfa) || 0) + (Number(materialsFcfa) || 0);

  return (
    <div className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle space-y-3">
      <div className="flex justify-between items-start gap-3">
        <h3 className="font-bold text-base text-foreground">
          {intervention.serviceRequest.tradeLabel}
        </h3>
        <span
          className={`px-2.5 py-0.5 rounded-full font-sora text-[11px] font-semibold shrink-0 ${STATUS_STYLES[intervention.status]}`}
        >
          {STATUS_LABELS[intervention.status]}
        </span>
      </div>

      <p className="text-sm text-muted-foreground line-clamp-2">
        {intervention.serviceRequest.description}
      </p>

      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      {/* proposee */}
      {intervention.status === 'proposee' && role === 'artisan' && (
        <div className="space-y-2 pt-1">
          {showDeclineForm ? (
            <div className="space-y-2">
              <textarea
                value={declineReason}
                onChange={(e) => setDeclineReason(e.target.value)}
                placeholder="Motif du refus (optionnel)"
                className="w-full h-20 p-3 rounded-xl bg-surface-muted text-sm outline-none focus:ring-2 focus:ring-primary resize-none"
              />
              <div className="flex gap-2">
                <button
                  disabled={isSubmitting}
                  onClick={() =>
                    runAction(() =>
                      api.declineIntervention(intervention.id, declineReason.trim() || null),
                    )
                  }
                  className="flex-1 py-2.5 rounded-full bg-destructive text-white font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
                >
                  Confirmer le refus
                </button>
                <button
                  disabled={isSubmitting}
                  onClick={() => setShowDeclineForm(false)}
                  className="px-4 py-2.5 rounded-full border border-border text-muted-foreground font-sora text-xs font-bold cursor-pointer"
                >
                  Annuler
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                disabled={isSubmitting}
                onClick={() => runAction(() => api.acceptIntervention(intervention.id))}
                className="flex-1 py-2.5 rounded-full bg-primary-emerald text-white font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
              >
                Accepter
              </button>
              <button
                disabled={isSubmitting}
                onClick={() => setShowDeclineForm(true)}
                className="flex-1 py-2.5 rounded-full border border-destructive text-destructive font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
              >
                Refuser
              </button>
            </div>
          )}
        </div>
      )}
      {intervention.status === 'proposee' && role === 'client' && (
        <p className="text-xs font-sora text-muted-foreground-soft">
          En attente de la réponse de l&apos;artisan.
        </p>
      )}

      {/* acceptee */}
      {intervention.status === 'acceptee' && (
        <>
          {intervention.quote && intervention.quote.status === 'propose' ? (
            role === 'client' ? (
              <div className="space-y-2 pt-1">
                <p className="text-sm font-sora font-semibold text-foreground">
                  Devis proposé : {formatFcfa(intervention.quote.totalFcfa)}
                </p>
                <div className="flex gap-2">
                  <button
                    disabled={isSubmitting}
                    onClick={() => runAction(() => api.acceptQuote(intervention.id))}
                    className="flex-1 py-2.5 rounded-full bg-primary-emerald text-white font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
                  >
                    Accepter le devis
                  </button>
                  <button
                    disabled={isSubmitting}
                    onClick={() => runAction(() => api.refuseQuote(intervention.id))}
                    className="flex-1 py-2.5 rounded-full border border-destructive text-destructive font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
                  >
                    Refuser
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-xs font-sora text-muted-foreground-soft pt-1">
                Devis envoyé ({formatFcfa(intervention.quote.totalFcfa)}), en attente de la réponse
                du client.
              </p>
            )
          ) : role === 'artisan' ? (
            <div className="space-y-2 pt-1">
              <div className="flex gap-2">
                <input
                  type="number"
                  min={0}
                  value={laborFcfa}
                  onChange={(e) => setLaborFcfa(e.target.value)}
                  placeholder="Main d'œuvre (FCFA)"
                  className="flex-1 h-11 px-3 rounded-xl bg-surface-muted text-sm outline-none focus:ring-2 focus:ring-primary"
                />
                <input
                  type="number"
                  min={0}
                  value={materialsFcfa}
                  onChange={(e) => setMaterialsFcfa(e.target.value)}
                  placeholder="Matériaux (FCFA)"
                  className="flex-1 h-11 px-3 rounded-xl bg-surface-muted text-sm outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <p className="text-xs font-sora text-muted-foreground-soft">
                Total : {formatFcfa(totalFcfa)}
              </p>
              <button
                disabled={isSubmitting || totalFcfa <= 0}
                onClick={() =>
                  runAction(() =>
                    api.createQuote(intervention.id, {
                      laborFcfa: Number(laborFcfa) || 0,
                      materialsFcfa: Number(materialsFcfa) || 0,
                    }),
                  )
                }
                className="w-full py-2.5 rounded-full bg-primary-emerald text-white font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
              >
                Envoyer le devis
              </button>
            </div>
          ) : (
            <p className="text-xs font-sora text-muted-foreground-soft pt-1">
              En attente du devis de l&apos;artisan.
            </p>
          )}
        </>
      )}

      {/* en_cours */}
      {intervention.status === 'en_cours' && (
        <div className="space-y-2 pt-1">
          {intervention.agreedAmountFcfa != null && (
            <p className="text-sm font-sora font-semibold text-foreground">
              Montant convenu : {formatFcfa(intervention.agreedAmountFcfa)}
            </p>
          )}
          {role === 'client' ? (
            <button
              disabled={isSubmitting}
              onClick={() => runAction(() => api.completeIntervention(intervention.id))}
              className="w-full py-2.5 rounded-full bg-primary-emerald text-white font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
            >
              Confirmer la fin des travaux
            </button>
          ) : (
            <p className="text-xs font-sora text-muted-foreground-soft">
              En attente de la confirmation du client.
            </p>
          )}
        </div>
      )}

      {/* terminee */}
      {intervention.status === 'terminee' && (
        <div className="space-y-2 pt-1">
          {intervention.review ? (
            <div className="bg-surface-muted rounded-xl p-3 space-y-1">
              <div className="flex items-center gap-1 text-accent-foreground">
                {[1, 2, 3, 4, 5].map((n) => (
                  <Star
                    key={n}
                    className="w-4 h-4"
                    {...(n <= intervention.review!.rating ? { fill: 'currentColor' } : {})}
                  />
                ))}
              </div>
              <p className="text-sm text-muted-foreground">{intervention.review.comment}</p>
            </div>
          ) : role === 'client' ? (
            <div className="space-y-2">
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setReviewRating(n)}
                    className="text-accent-foreground cursor-pointer"
                    aria-label={`${n} étoile${n > 1 ? 's' : ''}`}
                  >
                    <Star className="w-6 h-6" {...(n <= reviewRating ? { fill: 'currentColor' } : {})} />
                  </button>
                ))}
              </div>
              <textarea
                value={reviewComment}
                onChange={(e) => setReviewComment(e.target.value)}
                placeholder="Votre avis sur cette intervention..."
                className="w-full h-20 p-3 rounded-xl bg-surface-muted text-sm outline-none focus:ring-2 focus:ring-primary resize-none"
              />
              <button
                disabled={isSubmitting || reviewRating === 0 || reviewComment.trim().length === 0}
                onClick={() =>
                  runAction(() =>
                    api.createReview(intervention.id, {
                      rating: reviewRating,
                      comment: reviewComment.trim(),
                    }),
                  )
                }
                className="w-full py-2.5 rounded-full bg-primary-emerald text-white font-sora text-xs font-bold disabled:opacity-60 cursor-pointer"
              >
                Publier l&apos;avis
              </button>
            </div>
          ) : (
            <p className="text-xs font-sora text-muted-foreground-soft">
              Le client n&apos;a pas encore laissé d&apos;avis.
            </p>
          )}
        </div>
      )}

      {/* annulee */}
      {intervention.status === 'annulee' && (
        <p className="text-xs font-sora text-muted-foreground-soft pt-1">
          {role === 'client'
            ? "Cette mise en relation a été refusée par l'artisan."
            : 'Vous avez refusé cette mise en relation.'}
          {intervention.declineReason ? ` Motif : ${intervention.declineReason}` : ''}
        </p>
      )}
    </div>
  );
};
