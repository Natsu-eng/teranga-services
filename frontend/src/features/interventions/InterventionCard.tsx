import React, { useState } from 'react';
import { AlertTriangle, Check, MessageCircle, ReceiptText, XCircle } from 'lucide-react';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { TextAreaField, TextField } from '../../components/ui/Field';
import { RatingInput, StarRow } from '../../components/ui/Rating';
import { StatusPill } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { formatFcfa } from '../../lib/format';
import type { Intervention, UserRole } from '../../types';
import { PaymentPanel } from '../payments/components/PaymentPanel';
import { ProgressSteps } from './components/ProgressSteps';
import {
  DISPUTE_REASON_MIN_LENGTH,
  STATUS,
  STEP_INDEX,
  cancellationText,
  formatDate,
  partyLabel,
} from './interventionText';

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
  // Formulaire ouvert : annulation ou signalement d'un problème (litige).
  const [openForm, setOpenForm] = useState<'cancel' | 'dispute' | null>(null);
  const [formReason, setFormReason] = useState('');

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
  const { quote, payment, cancellation, dispute } = intervention;
  const fundsHeld = payment?.status === 'retenu';
  const checkoutOpen = payment?.status === 'en_attente' && payment.checkoutUrl !== null;
  const canCancel =
    role === 'client'
      ? ['proposee', 'acceptee', 'en_cours'].includes(intervention.status) && !fundsHeld
      : ['acceptee', 'en_cours'].includes(intervention.status);
  const canDispute = intervention.status === 'en_cours';
  const disputeReasonTooShort = formReason.trim().length < DISPUTE_REASON_MIN_LENGTH;

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

      {/* Paiement : montants et état, formulés pour chaque partie. */}
      {payment && (intervention.status !== 'annulee' || payment.status !== null) && (
        <PaymentPanel
          interventionId={intervention.id}
          interventionStatus={intervention.status}
          payment={payment}
          role={role}
        />
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
            <div className="space-y-2">
              {fundsHeld ? (
                <p className="text-sm text-muted-foreground">
                  Confirmer la fin des travaux verse le paiement à l&apos;artisan.
                </p>
              ) : checkoutOpen ? (
                <p className="text-sm text-muted-foreground">
                  Un paiement en ligne est en cours : terminez-le avant de confirmer la fin des
                  travaux.
                </p>
              ) : payment && payment.status !== 'reussi' ? (
                <p className="text-sm text-muted-foreground">
                  Sans paiement en ligne, vous réglez l&apos;artisan directement.
                </p>
              ) : null}
              <Button
                variant="brand"
                fullWidth
                isLoading={isSubmitting}
                disabled={checkoutOpen}
                onClick={() => runAction(() => api.completeIntervention(intervention.id))}
              >
                Confirmer la fin des travaux
              </Button>
            </div>
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

      {/* Discussion rattachée à cette mise en relation (les deux parties). */}
      {intervention.conversationId && (
        <ButtonLink
          to={`/messages/${intervention.conversationId}`}
          variant="ghost"
          size="sm"
          leadingIcon={<MessageCircle aria-hidden className="w-4 h-4" />}
        >
          {role === 'artisan' ? 'Discuter avec le client' : "Discuter avec l'artisan"}
        </ButtonLink>
      )}

      {/* litige : l'argent est gelé jusqu'à l'arbitrage */}
      {intervention.status === 'litige' && dispute && (
        <div className="rounded-field bg-destructive-soft p-3 space-y-1 text-sm">
          <p className="inline-flex items-center gap-1.5 font-semibold text-destructive">
            <AlertTriangle aria-hidden className="w-4 h-4" />
            Problème signalé {dispute.openedBy === role ? 'par vous' : partyLabel(dispute.openedBy)}
          </p>
          <p className="text-foreground">{dispute.reason}</p>
          <p className="text-muted-foreground">
            L&apos;argent est gelé : un conseiller Téranga examine la situation et tranchera
            (versement à l&apos;artisan ou remboursement du client).
          </p>
        </div>
      )}

      {dispute?.outcome && (
        <p className="text-sm text-muted-foreground">
          Litige tranché par Téranga :{' '}
          {dispute.outcome === 'libere'
            ? "paiement versé à l'artisan."
            : 'le client a été remboursé.'}
          {dispute.resolutionNote ? ` ${dispute.resolutionNote}` : ''}
        </p>
      )}

      {/* annulee : qui a clos, et pourquoi */}
      {intervention.status === 'annulee' && (
        <p className="text-sm text-muted-foreground">
          {cancellationText(intervention, role)}
          {cancellation?.reason && cancellation.kind !== 'arbitrage'
            ? ` Motif : ${cancellation.reason}`
            : ''}
        </p>
      )}

      {/* Annuler / signaler un problème : jamais d'action financière sans le dire. */}
      {openForm ? (
        <div className="space-y-3 rounded-field bg-surface-muted p-3">
          <p className="text-sm font-semibold text-foreground">
            {openForm === 'cancel' ? 'Annuler la mise en relation' : 'Signaler un problème'}
          </p>
          <p className="text-sm text-muted-foreground">
            {openForm === 'cancel'
              ? fundsHeld
                ? 'Le client sera intégralement remboursé ; aucune commission ne sera prélevée.'
                : "L'intervention sera close et la demande à nouveau ouverte."
              : "L'argent reste gelé jusqu'à la décision d'un conseiller Téranga. Expliquez la situation."}
          </p>
          <TextAreaField
            label={openForm === 'cancel' ? "Motif de l'annulation" : 'Description du problème'}
            value={formReason}
            onChange={(e) => setFormReason(e.target.value)}
            placeholder={
              openForm === 'cancel'
                ? 'Motif (optionnel)'
                : `Décrivez le problème (${DISPUTE_REASON_MIN_LENGTH} caractères minimum)`
            }
            rows={3}
          />
          <div className="flex gap-2">
            <Button
              variant="danger"
              className="flex-1"
              isLoading={isSubmitting}
              disabled={openForm === 'dispute' && disputeReasonTooShort}
              onClick={() =>
                runAction(() =>
                  openForm === 'cancel'
                    ? api.cancelIntervention(intervention.id, formReason.trim() || null)
                    : api.openDispute(intervention.id, formReason.trim()),
                )
              }
            >
              {openForm === 'cancel' ? "Confirmer l'annulation" : 'Envoyer le signalement'}
            </Button>
            <Button
              variant="ghost"
              disabled={isSubmitting}
              onClick={() => {
                setOpenForm(null);
                setFormReason('');
              }}
            >
              Retour
            </Button>
          </div>
        </div>
      ) : (
        (canCancel || canDispute) && (
          <div className="flex flex-wrap gap-2">
            {canDispute && (
              <Button
                variant="ghost"
                size="sm"
                leadingIcon={<AlertTriangle aria-hidden className="w-4 h-4" />}
                onClick={() => setOpenForm('dispute')}
              >
                Signaler un problème
              </Button>
            )}
            {canCancel && (
              <Button
                variant="danger-ghost"
                size="sm"
                leadingIcon={<XCircle aria-hidden className="w-4 h-4" />}
                onClick={() => setOpenForm('cancel')}
              >
                Annuler
              </Button>
            )}
          </div>
        )
      )}
    </Card>
  );
};
