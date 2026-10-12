import React, { useState } from 'react';
import { ClipboardList, MapPin, Search, TriangleAlert, XCircle } from 'lucide-react';
import { AppBar } from '../../components/ui/AppBar';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill, type StatusTone } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { formatFcfa } from '../../lib/format';
import { isInServiceRegion } from '../../lib/places';
import type { ServiceRequest, ServiceRequestStatus } from '../../types';
import { useMyRequests } from './hooks/useMyRequests';

const STATUS: Record<ServiceRequestStatus, { label: string; tone: StatusTone }> = {
  ouverte: { label: "En attente d'un artisan", tone: 'warning' },
  en_relation: { label: 'Mise en relation en cours', tone: 'info' },
  convertie: { label: 'Travaux en cours', tone: 'success' },
  annulee: { label: 'Annulée', tone: 'danger' },
  expiree: { label: 'Expirée', tone: 'neutral' },
};

/** Demandes encore actives ; les autres vont dans « Anciennes demandes ». */
const ACTIVE_STATUSES: ReadonlySet<ServiceRequestStatus> = new Set([
  'ouverte',
  'en_relation',
  'convertie',
]);

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

interface RequestCardProps {
  request: ServiceRequest;
  onCancelled: () => void;
}

/**
 * Une demande. Ouverte : « Choisir un artisan » et « Annuler la demande »
 * (avec confirmation : elle ne sera plus proposée aux artisans, mais reste
 * dans l'historique). Localisée hors de la région de Dakar : le dire, et
 * proposer directement de l'annuler.
 */
const RequestCard: React.FC<RequestCardProps> = ({ request, onCancelled }) => {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const isOpen = request.status === 'ouverte';
  const outOfRegion = isOpen && !isInServiceRegion(request.location);

  const cancel = async () => {
    setCancelError(null);
    setIsCancelling(true);
    try {
      await api.cancelServiceRequest(request.id);
      onCancelled();
    } catch (err) {
      setCancelError(
        err instanceof ApiError ? err.message : "L'annulation n'a pas pu aboutir. Réessayez.",
      );
      setIsCancelling(false);
    }
  };

  return (
    <Card as="article" className="space-y-3">
      <div className="space-y-1">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-title font-semibold text-foreground">
            {request.tradeLabel}
          </h2>
          <StatusPill tone={STATUS[request.status].tone}>{STATUS[request.status].label}</StatusPill>
        </div>
        <p className="text-xs text-muted-foreground">Créée le {formatDate(request.createdAt)}</p>
        <p className="flex items-center gap-1 text-xs text-muted-foreground">
          <MapPin aria-hidden className="w-3.5 h-3.5 shrink-0" />
          Lieu : {request.locationLabel ?? 'position GPS enregistrée'}
        </p>
      </div>
      {outOfRegion && (
        <p className="flex items-start gap-2 rounded-field bg-accent-soft p-3 text-sm text-foreground">
          <TriangleAlert aria-hidden className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Cette demande est localisée hors de la région de Dakar : aucun artisan ne pourra la
            recevoir. Annulez-la, puis décrivez à nouveau votre besoin en choisissant le quartier
            des travaux.
          </span>
        </p>
      )}
      <p className="text-sm text-muted-foreground line-clamp-3">{request.description}</p>
      {request.aiEstimateMinFcfa != null && request.aiEstimateMaxFcfa != null && (
        <p className="text-sm text-foreground">
          Estimation :{' '}
          <span className="font-semibold">
            {formatFcfa(request.aiEstimateMinFcfa)} – {formatFcfa(request.aiEstimateMaxFcfa)}
          </span>
        </p>
      )}

      {isOpen &&
        (isConfirming ? (
          <div
            className="space-y-3 rounded-field bg-surface-muted p-3"
            role="group"
            aria-label="Annuler la demande"
          >
            <p className="text-sm text-foreground">
              Cette demande ne sera plus proposée aux artisans. Elle restera visible dans vos
              anciennes demandes.
            </p>
            {cancelError && (
              <p role="alert" className="text-sm text-destructive">
                {cancelError}
              </p>
            )}
            <div className="flex gap-2">
              <Button variant="danger" className="flex-1" isLoading={isCancelling} onClick={cancel}>
                Confirmer l&apos;annulation
              </Button>
              <Button
                variant="ghost"
                disabled={isCancelling}
                onClick={() => {
                  setIsConfirming(false);
                  setCancelError(null);
                }}
              >
                Garder la demande
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {!outOfRegion && (
              <ButtonLink
                to={searchUrlFor(request)}
                variant="primary"
                fullWidth
                leadingIcon={<Search aria-hidden className="w-4 h-4" />}
              >
                Choisir un artisan
              </ButtonLink>
            )}
            <Button
              variant={outOfRegion ? 'danger-outline' : 'danger-ghost'}
              size="sm"
              fullWidth={outOfRegion}
              leadingIcon={<XCircle aria-hidden className="w-4 h-4" />}
              onClick={() => setIsConfirming(true)}
            >
              {outOfRegion ? 'Annuler cette demande' : 'Annuler la demande'}
            </Button>
          </div>
        ))}

      {(request.status === 'en_relation' || request.status === 'convertie') && (
        <ButtonLink to="/mes-interventions" variant="outline" fullWidth>
          Voir le devis et le suivi
        </ButtonLink>
      )}
    </Card>
  );
};

/**
 * Demandes du client (/mes-demandes). Les demandes actives d'abord ; une
 * demande OUVERTE attend un artisan (« Choisir un artisan ») ou peut être
 * annulée. Annulées et expirées restent consultables, repliées sous
 * « Anciennes demandes » : elles ne s'accumulent plus sous les yeux.
 */
export const MyRequestsScreen: React.FC = () => {
  const { data: requests, isLoading, error, reload } = useMyRequests();
  const active = (requests ?? []).filter((request) => ACTIVE_STATUSES.has(request.status));
  const archived = (requests ?? []).filter((request) => !ACTIVE_STATUSES.has(request.status));

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
        ) : (
          <>
            {active.length === 0 ? (
              <EmptyState
                icon={<ClipboardList />}
                title={
                  archived.length === 0
                    ? "Vous n'avez pas encore de demande."
                    : "Vous n'avez aucune demande en cours."
                }
                description="Décrivez votre problème à notre assistant IA pour trouver un artisan."
              >
                <ButtonLink to="/demande" variant="primary" size="sm">
                  Décrire mon problème
                </ButtonLink>
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {active.map((request) => (
                  <li key={request.id}>
                    <RequestCard request={request} onCancelled={reload} />
                  </li>
                ))}
              </ul>
            )}

            {archived.length > 0 && (
              <details className="group rounded-card bg-surface-muted p-3">
                <summary className="cursor-pointer text-sm font-semibold text-foreground">
                  Anciennes demandes ({archived.length})
                </summary>
                <ul className="mt-3 space-y-3">
                  {archived.map((request) => (
                    <li key={request.id}>
                      <RequestCard request={request} onCancelled={reload} />
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </main>
    </>
  );
};
