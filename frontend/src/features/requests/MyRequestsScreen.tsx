import React from 'react';
import { ClipboardList, Search } from 'lucide-react';
import { AppBar } from '../../components/ui/AppBar';
import { ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill, type StatusTone } from '../../components/ui/StatusPill';
import { formatFcfa } from '../../lib/format';
import type { ServiceRequest, ServiceRequestStatus } from '../../types';
import { useMyRequests } from './hooks/useMyRequests';

const STATUS: Record<ServiceRequestStatus, { label: string; tone: StatusTone }> = {
  ouverte: { label: "En attente d'un artisan", tone: 'warning' },
  en_relation: { label: 'Mise en relation en cours', tone: 'info' },
  convertie: { label: 'Travaux en cours', tone: 'success' },
  annulee: { label: 'Annulée', tone: 'danger' },
  expiree: { label: 'Expirée', tone: 'neutral' },
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** Recherche filtrée sur le métier et le lieu de la demande (filtres serveur). */
function searchUrlFor(request: ServiceRequest): string {
  const { lat, lng } = request.location;
  return `/recherche?trade=${encodeURIComponent(request.tradeCode)}&lat=${lat}&lng=${lng}`;
}

/**
 * Demandes du client (/mes-demandes). Une demande OUVERTE attend un
 * artisan : « Choisir un artisan » mène aux artisans de son métier près du
 * lieu indiqué, d'où le client demande un devis (fiche artisan).
 */
export const MyRequestsScreen: React.FC = () => {
  const { data: requests, isLoading, error, reload } = useMyRequests();

  return (
    <>
      <AppBar title="Mes demandes" backTo="/profil" />
      <main className="w-full max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-10 space-y-4">
        {isLoading && requests === null ? (
          <div className="space-y-3" aria-busy="true">
            {[0, 1, 2].map((key) => (
              <Card key={key} className="space-y-3">
                <Skeleton className="h-5 w-1/2" />
                <Skeleton className="h-3 w-3/4" />
              </Card>
            ))}
          </div>
        ) : error && requests === null ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : requests && requests.length === 0 ? (
          <EmptyState
            icon={<ClipboardList />}
            title="Vous n'avez pas encore de demande."
            description="Décrivez votre problème à notre assistant IA pour trouver un artisan."
          >
            <ButtonLink to="/demande" variant="primary" size="sm">
              Décrire mon problème
            </ButtonLink>
          </EmptyState>
        ) : (
          <ul className="space-y-3">
            {(requests ?? []).map((request) => (
              <li key={request.id}>
                <Card as="article" className="space-y-3">
                  <div className="space-y-1">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="font-display text-title font-semibold text-foreground">
                        {request.tradeLabel}
                      </h2>
                      <StatusPill tone={STATUS[request.status].tone}>
                        {STATUS[request.status].label}
                      </StatusPill>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Créée le {formatDate(request.createdAt)}
                    </p>
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-3">
                    {request.description}
                  </p>
                  {request.aiEstimateMinFcfa != null && request.aiEstimateMaxFcfa != null && (
                    <p className="text-sm text-foreground">
                      Estimation :{' '}
                      <span className="font-semibold">
                        {formatFcfa(request.aiEstimateMinFcfa)} –{' '}
                        {formatFcfa(request.aiEstimateMaxFcfa)}
                      </span>
                    </p>
                  )}
                  {request.status === 'ouverte' && (
                    <ButtonLink
                      to={searchUrlFor(request)}
                      variant="primary"
                      fullWidth
                      leadingIcon={<Search aria-hidden className="w-4 h-4" />}
                    >
                      Choisir un artisan
                    </ButtonLink>
                  )}
                  {(request.status === 'en_relation' || request.status === 'convertie') && (
                    <ButtonLink to="/mes-interventions" variant="outline" fullWidth>
                      Voir le devis et le suivi
                    </ButtonLink>
                  )}
                </Card>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
};
