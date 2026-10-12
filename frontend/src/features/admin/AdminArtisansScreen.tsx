import React, { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { ChevronRight, HardHat, Star } from 'lucide-react';
import { Card } from '../../components/ui/Card';
import { Chip } from '../../components/ui/Chip';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { AdminArtisanListItem, AdminArtisanStatusFilter, PageResult } from '../../types/admin';
import { VERIFIED_STATUS } from './adminText';
import { Pager } from './components/Pager';
import { SearchBar } from './components/SearchBar';

const FILTERS: { value: AdminArtisanStatusFilter | null; label: string }[] = [
  { value: null, label: 'Tous' },
  { value: 'pending', label: 'À vérifier' },
  { value: 'verified', label: 'Vérifiés' },
  { value: 'none', label: 'Incomplets' },
  { value: 'rejected', label: 'Refusés' },
  { value: 'suspended', label: 'Suspendus' },
];

const ArtisanRow: React.FC<{ artisan: AdminArtisanListItem }> = ({ artisan }) => (
  <li>
    <Link
      to={`/admin/artisans/${artisan.id}`}
      className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-emerald-tint"
    >
      <span className="min-w-0 space-y-1">
        <span className="block font-medium text-foreground truncate">{artisan.fullName}</span>
        <span className="block text-sm text-muted-foreground truncate">
          {artisan.phone}
          {artisan.tradeLabels.length > 0 ? ` · ${artisan.tradeLabels.join(', ')}` : ''}
        </span>
        <span className="flex flex-wrap items-center gap-2">
          {artisan.isSuspended ? (
            <StatusPill tone="danger">Suspendu</StatusPill>
          ) : (
            <StatusPill tone={VERIFIED_STATUS[artisan.verifiedStatus].tone}>
              {VERIFIED_STATUS[artisan.verifiedStatus].label}
            </StatusPill>
          )}
          {artisan.pendingDocuments > 0 && (
            <span className="text-xs text-accent-foreground-strong">
              {artisan.pendingDocuments} document{artisan.pendingDocuments > 1 ? 's' : ''} à
              examiner
            </span>
          )}
          {artisan.reviewCount > 0 && artisan.ratingAvg !== null && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Star aria-hidden className="w-3 h-3" />
              {artisan.ratingAvg.toFixed(1).replace('.', ',')} ({artisan.reviewCount} avis)
            </span>
          )}
        </span>
      </span>
      <ChevronRight aria-hidden className="w-4 h-4 shrink-0 text-muted-foreground" />
    </Link>
  </li>
);

/**
 * Artisans (/admin/artisans) : tous, vérifiés ou non, suspendus compris,
 * filtrables par statut et cherchables par nom ou téléphone.
 */
export const AdminArtisansScreen: React.FC = () => {
  const [status, setStatus] = useState<AdminArtisanStatusFilter | null>(null);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const { data, isLoading, error, run, reload } =
    useAsyncResource<PageResult<AdminArtisanListItem>>();

  useEffect(() => {
    run(() => api.listAdminArtisans({ status: status ?? undefined, q, page }));
  }, [run, status, q, page]);

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-display-md font-semibold text-primary">Artisans</h1>
        <p className="text-sm text-muted-foreground">
          Un artisan suspendu disparaît de la recherche et ne reçoit plus de demandes ; ses
          interventions en cours continuent.
        </p>
      </div>

      <SearchBar
        label="Rechercher un artisan"
        placeholder="Nom ou téléphone"
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
        <Skeleton className="h-64 rounded-card" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon={<HardHat />}
          title={q || status ? 'Aucun artisan ne correspond.' : 'Aucun artisan inscrit.'}
        />
      ) : data ? (
        <>
          <Card padding="none" className="overflow-hidden">
            <ul className="divide-y divide-border">
              {data.items.map((artisan) => (
                <ArtisanRow key={artisan.id} artisan={artisan} />
              ))}
            </ul>
          </Card>
          <Pager
            page={data.page}
            totalPages={data.totalPages}
            total={data.total}
            onPageChange={setPage}
          />
        </>
      ) : null}
    </div>
  );
};
