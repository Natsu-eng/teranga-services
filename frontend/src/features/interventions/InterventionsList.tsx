import React from 'react';
import { ClipboardList } from 'lucide-react';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { InterventionCard } from './InterventionCard';
import { useMyInterventions } from './hooks/useMyInterventions';
import type { Intervention, InterventionStatus } from '../../types';

const STATUS_ORDER: InterventionStatus[] = [
  'proposee',
  'acceptee',
  'en_cours',
  'terminee',
  'annulee',
  'litige',
];

const STATUS_GROUP_LABELS: Record<InterventionStatus, string> = {
  proposee: 'En attente de réponse',
  acceptee: 'Devis en cours',
  en_cours: 'En cours',
  terminee: 'Terminées',
  annulee: 'Refusées ou annulées',
  litige: 'Litiges',
};

function groupInterventionsByStatus(
  interventions: Intervention[],
): Record<InterventionStatus, Intervention[]> {
  const grouped = Object.fromEntries(
    STATUS_ORDER.map((status) => [status, [] as Intervention[]]),
  ) as Record<InterventionStatus, Intervention[]>;
  for (const intervention of interventions) {
    grouped[intervention.status].push(intervention);
  }
  return grouped;
}

interface InterventionsListProps {
  /** Text shown when `GET /interventions/me` resolves to an empty list. */
  emptyTitle: string;
  /**
   * Groups cards under a heading per status (artisan dashboard, `/pro`)
   * instead of one flat chronological list (client `/mes-interventions`,
   * the default) -- same data, same cards, just a different layout.
   */
  groupByStatus?: boolean;
}

// Shared by InterventionsScreen (`/mes-interventions`) and
// ArtisanDashboardScreen (`/pro`): both need the same fetch/loading/error/
// empty handling and the same InterventionCard rendering, just laid out
// differently (flat vs grouped by status) -- factored out once here rather
// than duplicated.
export const InterventionsList: React.FC<InterventionsListProps> = ({
  emptyTitle,
  groupByStatus: shouldGroup = false,
}) => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);
  const { data: interventions, isLoading, error, reload } = useMyInterventions();

  if (isLoading && interventions === null) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((key) => (
          <div
            key={key}
            className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle space-y-2"
          >
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  if (error && interventions === null) {
    return <ErrorState message={error.message} onRetry={reload} />;
  }

  if (interventions && interventions.length === 0) {
    return (
      <EmptyState
        icon={<ClipboardList className="text-muted-foreground-soft mb-2 w-9 h-9 mx-auto" />}
        title={emptyTitle}
      />
    );
  }

  const list = interventions ?? [];

  if (!shouldGroup) {
    return (
      <div className="space-y-4">
        {list.map((intervention) => (
          <InterventionCard
            key={intervention.id}
            intervention={intervention}
            role={role}
            onChanged={reload}
          />
        ))}
      </div>
    );
  }

  const grouped = groupInterventionsByStatus(list);
  return (
    <div className="space-y-6">
      {STATUS_ORDER.filter((status) => grouped[status].length > 0).map((status) => (
        <section key={status} className="space-y-3">
          <h3 className="font-sora text-xs font-bold uppercase tracking-wider text-muted-foreground-soft">
            {STATUS_GROUP_LABELS[status]}
          </h3>
          <div className="space-y-4">
            {grouped[status].map((intervention) => (
              <InterventionCard
                key={intervention.id}
                intervention={intervention}
                role={role}
                onChanged={reload}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
};
