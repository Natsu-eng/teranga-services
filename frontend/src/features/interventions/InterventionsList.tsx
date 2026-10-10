import React from 'react';
import { ClipboardList } from 'lucide-react';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
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
  /** Texte affiché quand `GET /interventions/me` renvoie une liste vide. */
  emptyTitle: string;
  emptyDescription?: string;
  /** Action proposée dans l'état vide (ex. « Décrire mon besoin » côté client). */
  emptyAction?: React.ReactNode;
  /**
   * Regroupe les cartes sous un intertitre par statut (tableau de bord
   * artisan, `/pro`) au lieu d'une liste chronologique (client,
   * `/mes-interventions`) : mêmes données, mêmes cartes.
   */
  groupByStatus?: boolean;
}

// Partagé par InterventionsScreen (`/mes-interventions`) et
// ArtisanDashboardScreen (`/pro`) : même chargement / erreur / vide et
// même carte, seule la disposition change.
export const InterventionsList: React.FC<InterventionsListProps> = ({
  emptyTitle,
  emptyDescription,
  emptyAction,
  groupByStatus: shouldGroup = false,
}) => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);
  const { data: interventions, isLoading, error, reload } = useMyInterventions();

  if (isLoading && interventions === null) {
    return (
      <div className="space-y-3" aria-busy="true">
        {[0, 1, 2].map((key) => (
          <Card key={key} className="space-y-3">
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-1.5 w-full" />
          </Card>
        ))}
      </div>
    );
  }

  if (error && interventions === null) {
    return <ErrorState message={error.message} onRetry={reload} />;
  }

  if (interventions && interventions.length === 0) {
    return (
      <EmptyState icon={<ClipboardList />} title={emptyTitle} description={emptyDescription}>
        {emptyAction}
      </EmptyState>
    );
  }

  const list = interventions ?? [];

  if (!shouldGroup) {
    return (
      <ul className="space-y-4">
        {list.map((intervention) => (
          <li key={intervention.id}>
            <InterventionCard intervention={intervention} role={role} onChanged={reload} />
          </li>
        ))}
      </ul>
    );
  }

  const grouped = groupInterventionsByStatus(list);
  return (
    <div className="space-y-6">
      {STATUS_ORDER.filter((status) => grouped[status].length > 0).map((status) => (
        <section key={status} aria-label={STATUS_GROUP_LABELS[status]} className="space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="text-caption font-semibold uppercase tracking-wider text-muted-foreground">
              {STATUS_GROUP_LABELS[status]}
            </h3>
            <span className="inline-flex min-w-5 h-5 items-center justify-center rounded-full bg-surface-muted px-1.5 text-caption font-semibold text-muted-foreground">
              {grouped[status].length}
            </span>
          </div>
          <ul className="space-y-4">
            {grouped[status].map((intervention) => (
              <li key={intervention.id}>
                <InterventionCard intervention={intervention} role={role} onChanged={reload} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
};
