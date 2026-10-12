import React, { useEffect, useState } from 'react';
import { Flag, Star } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { TextAreaField } from '../../components/ui/Field';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Sheet } from '../../components/ui/Sheet';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { MyReceivedReview } from '../../types';

/** Longueur minimale du motif, alignée sur la validation serveur. */
const REPORT_MIN_LENGTH = 10;

const STATUS = {
  publie: null,
  signale: { label: 'Signalé · en cours d’examen', tone: 'warning' },
  masque: { label: 'Masqué par la modération', tone: 'neutral' },
} as const;

const ReportSheet: React.FC<{
  review: MyReceivedReview | null;
  onClose: () => void;
  onReported: (review: MyReceivedReview) => void;
}> = ({ review, onClose, onReported }) => {
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    if (isSubmitting) return;
    setReason('');
    setError(null);
    onClose();
  };

  const submit = async () => {
    if (!review || reason.trim().length < REPORT_MIN_LENGTH) return;
    setError(null);
    setIsSubmitting(true);
    try {
      onReported(await api.reportReview(review.id, reason.trim()));
      setReason('');
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Signalement impossible. Réessayez.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Sheet open={review !== null} onClose={close} title="Signaler cet avis">
      <div className="space-y-4">
        <p className="text-sm text-foreground">
          Un administrateur examinera votre signalement. En attendant sa décision, l’avis reste
          visible et compte dans votre note. Vous ne pouvez signaler un avis qu’une seule fois.
        </p>
        <TextAreaField
          label="Pourquoi cet avis pose-t-il problème ?"
          hint={`${REPORT_MIN_LENGTH} caractères minimum. Lu par l’équipe Téranga.`}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={3}
          maxLength={1000}
        />
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            variant="brand"
            className="flex-1"
            isLoading={isSubmitting}
            disabled={reason.trim().length < REPORT_MIN_LENGTH}
            onClick={submit}
          >
            Envoyer le signalement
          </Button>
          <Button variant="ghost" disabled={isSubmitting} onClick={close}>
            Annuler
          </Button>
        </div>
      </div>
    </Sheet>
  );
};

/**
 * Avis reçus (espace Pro) : tous, masqués compris, avec leur statut de
 * modération — l'artisan sait ce qui a été décidé à son sujet. Il peut
 * signaler un avis qu'il estime abusif ; seul un admin peut le masquer.
 */
export const MyReviewsSection: React.FC = () => {
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<MyReceivedReview[]>();
  const [reporting, setReporting] = useState<MyReceivedReview | null>(null);

  useEffect(() => {
    run(() => api.listMyReviews());
  }, [run]);

  const replace = (updated: MyReceivedReview) =>
    setData((prev) => (prev ? prev.map((r) => (r.id === updated.id ? updated : r)) : prev));

  return (
    <section aria-labelledby="avis-recus" className="space-y-4">
      <SectionHeader id="avis-recus" title="Avis reçus" />
      {isLoading && !data ? (
        <Skeleton className="h-32 rounded-card" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data && data.length === 0 ? (
        <EmptyState icon={<Star />} title="Pas encore d’avis." />
      ) : (
        <ul className="space-y-3">
          {(data ?? []).map((review) => {
            const status = STATUS[review.status];
            return (
              <li key={review.id}>
                <Card as="article" padding="md" className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold text-foreground">
                      {review.rating}/5 · {review.authorName}
                    </p>
                    {status && <StatusPill tone={status.tone}>{status.label}</StatusPill>}
                  </div>
                  <p className="text-sm text-foreground whitespace-pre-line">{review.comment}</p>
                  {review.reportReason && (
                    <p className="text-xs text-muted-foreground">
                      Votre signalement : {review.reportReason}
                    </p>
                  )}
                  {review.canReport && (
                    <Button
                      variant="ghost"
                      size="sm"
                      leadingIcon={<Flag aria-hidden className="w-4 h-4" />}
                      onClick={() => setReporting(review)}
                    >
                      Signaler cet avis
                    </Button>
                  )}
                </Card>
              </li>
            );
          })}
        </ul>
      )}
      <ReportSheet review={reporting} onClose={() => setReporting(null)} onReported={replace} />
    </section>
  );
};
