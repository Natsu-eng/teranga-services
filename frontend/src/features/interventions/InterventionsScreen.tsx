import React from 'react';
import { ClipboardList } from 'lucide-react';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { InterventionCard } from './InterventionCard';
import { useMyInterventions } from './hooks/useMyInterventions';

// Un seul écran pour les deux rôles : GET /interventions/me s'adapte déjà
// côté serveur (client -> ses interventions, artisan -> celles qui le
// concernent, Lot 12a). C'est le premier vrai contenu de l'espace Artisan
// Pro (AUDIT_PHASE2.md §6 Lot 12b) : de vraies demandes reçues, pas un
// placeholder.
export const InterventionsScreen: React.FC = () => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);
  const { data: interventions, isLoading, error, reload } = useMyInterventions();

  return (
    <main className="max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      <h2 className="font-bold text-2xl text-primary">
        {role === 'artisan' ? 'Mes demandes reçues' : 'Mes interventions'}
      </h2>

      {isLoading && interventions === null ? (
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
      ) : error && interventions === null ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : interventions && interventions.length === 0 ? (
        <EmptyState
          icon={<ClipboardList className="text-muted-foreground-soft mb-2 w-9 h-9 mx-auto" />}
          title={
            role === 'artisan'
              ? "Aucune demande reçue pour l'instant."
              : 'Aucune intervention en cours.'
          }
        />
      ) : (
        <div className="space-y-4">
          {(interventions ?? []).map((intervention) => (
            <InterventionCard
              key={intervention.id}
              intervention={intervention}
              role={role}
              onChanged={reload}
            />
          ))}
        </div>
      )}
    </main>
  );
};
