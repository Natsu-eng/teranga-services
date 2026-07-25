import React from 'react';
import { ClipboardList } from 'lucide-react';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { useMyRequests } from './hooks/useMyRequests';
import type { ServiceRequestStatus } from '../../types';

const STATUS_LABELS: Record<ServiceRequestStatus, string> = {
  ouverte: "En attente d'un artisan",
  en_relation: 'Mise en relation en cours',
  convertie: 'Intervention en cours',
  annulee: 'Annulée',
  expiree: 'Expirée',
};

const STATUS_STYLES: Record<ServiceRequestStatus, string> = {
  ouverte: 'bg-accent-soft/50 text-accent-foreground',
  en_relation: 'bg-primary-emerald/10 text-primary',
  convertie: 'bg-success/10 text-success',
  annulee: 'bg-destructive-soft/30 text-destructive',
  expiree: 'bg-surface-muted text-muted-foreground',
};

export const MyRequestsScreen: React.FC = () => {
  const { data: requests, isLoading, error, reload } = useMyRequests();

  return (
    <main className="max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      <h2 className="font-bold text-2xl text-primary">Mes demandes</h2>

      {isLoading && requests === null ? (
        <div className="space-y-3">
          {[0, 1, 2].map((key) => (
            <div
              key={key}
              className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle space-y-2"
            >
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          ))}
        </div>
      ) : error && requests === null ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : requests && requests.length === 0 ? (
        <EmptyState
          icon={<ClipboardList className="text-muted-foreground-soft mb-2 w-9 h-9 mx-auto" />}
          title="Vous n'avez pas encore de demande."
          description="Décrivez votre problème à notre assistant IA pour trouver un artisan."
        />
      ) : (
        <div className="space-y-3">
          {(requests ?? []).map((request) => (
            <div
              key={request.id}
              className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle space-y-2"
            >
              <div className="flex justify-between items-start gap-3">
                <h3 className="font-bold text-base text-foreground">{request.tradeLabel}</h3>
                <span
                  className={`px-2.5 py-0.5 rounded-full font-sora text-[11px] font-semibold shrink-0 ${STATUS_STYLES[request.status]}`}
                >
                  {STATUS_LABELS[request.status]}
                </span>
              </div>
              <p className="text-sm text-muted-foreground line-clamp-2">{request.description}</p>
            </div>
          ))}
        </div>
      )}
    </main>
  );
};
