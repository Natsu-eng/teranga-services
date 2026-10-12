import React, { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { EyeOff, MessageSquareWarning, RotateCcw, Star } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Chip } from '../../components/ui/Chip';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { AdminReview, PageResult, ReviewModerationStatus } from '../../types/admin';
import { REASON_MIN_LENGTH, REVIEW_STATUS, formatAdminDateTime } from './adminText';
import { ConfirmActionSheet } from './components/ConfirmActionSheet';
import { Pager } from './components/Pager';
import { SearchBar } from './components/SearchBar';

const FILTERS: { value: ReviewModerationStatus | null; label: string }[] = [
  { value: 'signale', label: 'Signalés' },
  { value: null, label: 'Tous' },
  { value: 'publie', label: 'Publiés' },
  { value: 'masque', label: 'Masqués' },
];

const ReviewCard: React.FC<{
  review: AdminReview;
  onAction: (action: 'hide' | 'restore') => void;
}> = ({ review, onAction }) => (
  <Card as="article" padding="lg" className="space-y-3">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="flex items-center gap-1 font-semibold text-foreground">
          <Star aria-hidden className="w-4 h-4" />
          {review.rating}/5 · {review.authorName}
          {review.contactVerified && (
            <span className="text-xs font-normal text-muted-foreground"> · contact vérifié</span>
          )}
        </p>
        <p className="text-sm text-muted-foreground">
          Pour{' '}
          <Link
            to={`/admin/artisans/${review.artisanId}`}
            className="font-medium text-primary underline"
          >
            {review.artisanName}
          </Link>{' '}
          · {formatAdminDateTime(review.createdAt)}
        </p>
      </div>
      <StatusPill tone={REVIEW_STATUS[review.status].tone}>
        {REVIEW_STATUS[review.status].label}
      </StatusPill>
    </div>

    <p className="text-sm text-foreground whitespace-pre-line">{review.comment}</p>

    {review.reportReason && (
      <p className="rounded-field bg-accent-soft p-3 text-sm text-foreground">
        <span className="font-semibold">Signalé par l’artisan</span>
        {review.reportedAt ? ` le ${formatAdminDateTime(review.reportedAt)}` : ''} :{' '}
        {review.reportReason}
      </p>
    )}

    <div className="flex flex-wrap gap-2">
      {review.status !== 'masque' && (
        <Button
          variant="danger-outline"
          size="sm"
          leadingIcon={<EyeOff aria-hidden className="w-4 h-4" />}
          onClick={() => onAction('hide')}
        >
          Masquer
        </Button>
      )}
      {review.status !== 'publie' && (
        <Button
          variant="outline"
          size="sm"
          leadingIcon={<RotateCcw aria-hidden className="w-4 h-4" />}
          onClick={() => onAction('restore')}
        >
          {review.status === 'signale' ? 'Maintenir l’avis' : 'Rétablir'}
        </Button>
      )}
    </div>
  </Card>
);

/**
 * Modération des avis (/admin/avis). Un avis n'est jamais supprimé : on le
 * masque (motif obligatoire) ou on le maintient/rétablit ; la note de
 * l'artisan est recalculée par le serveur et chaque décision journalisée.
 * Les avis signalés s'affichent d'abord : ils attendent une décision.
 */
export const AdminReviewsScreen: React.FC = () => {
  const [status, setStatus] = useState<ReviewModerationStatus | null>('signale');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<{
    review: AdminReview;
    action: 'hide' | 'restore';
  } | null>(null);
  const { data, isLoading, error, run, reload, setData } =
    useAsyncResource<PageResult<AdminReview>>();

  useEffect(() => {
    run(() => api.listAdminReviews({ status: status ?? undefined, q, page }));
  }, [run, status, q, page]);

  const replace = (updated: AdminReview) =>
    setData((prev) =>
      prev
        ? { ...prev, items: prev.items.map((item) => (item.id === updated.id ? updated : item)) }
        : prev,
    );

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-display-md font-semibold text-primary">Avis</h1>
        <p className="text-sm text-muted-foreground">
          Un avis signalé reste visible et compté tant que vous n’avez pas décidé.
        </p>
      </div>

      <SearchBar
        label="Rechercher un avis"
        placeholder="Texte de l’avis ou nom de l’auteur"
        onSearch={(value) => {
          setQ(value);
          setPage(1);
        }}
      />
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrer par statut">
        {FILTERS.map((filter) => (
          <Chip
            key={filter.label}
            selected={status === filter.value}
            onClick={() => {
              setStatus(filter.value);
              setPage(1);
            }}
          >
            {filter.label}
          </Chip>
        ))}
      </div>

      {isLoading && !data ? (
        <Skeleton className="h-52 rounded-card" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon={<MessageSquareWarning />}
          title={status === 'signale' ? 'Aucun avis signalé.' : 'Aucun avis ne correspond.'}
        />
      ) : data ? (
        <>
          <ul className="space-y-4">
            {data.items.map((review) => (
              <li key={review.id}>
                <ReviewCard review={review} onAction={(action) => setPending({ review, action })} />
              </li>
            ))}
          </ul>
          <Pager
            page={data.page}
            totalPages={data.totalPages}
            total={data.total}
            onPageChange={setPage}
          />
        </>
      ) : null}

      <ConfirmActionSheet
        open={pending?.action === 'hide'}
        onClose={() => setPending(null)}
        title="Masquer cet avis"
        tone="danger"
        confirmLabel="Masquer l’avis"
        effect="L’avis disparaît de la fiche publique et sort de la note de l’artisan. Il n’est pas supprimé : vous pourrez le rétablir."
        reason={{ label: 'Motif du masquage', mode: 'required', minLength: REASON_MIN_LENGTH }}
        onConfirm={async (reason) => {
          if (!pending) return;
          replace(await api.hideReview(pending.review.id, reason));
        }}
      />
      <ConfirmActionSheet
        open={pending?.action === 'restore'}
        onClose={() => setPending(null)}
        title={pending?.review.status === 'signale' ? 'Maintenir cet avis' : 'Rétablir cet avis'}
        confirmLabel={pending?.review.status === 'signale' ? 'Maintenir l’avis' : 'Rétablir l’avis'}
        effect="L’avis est publié et compté dans la note de l’artisan."
        reason={{ label: 'Note', mode: 'optional' }}
        onConfirm={async (note) => {
          if (!pending) return;
          replace(await api.restoreReview(pending.review.id, note));
        }}
      />
    </div>
  );
};
