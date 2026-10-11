import React, { useEffect, useState } from 'react';
import { CheckCircle2, ClipboardList, MapPin, Send } from 'lucide-react';
import { Button, ButtonLink } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { ErrorState } from '../../../components/ui/ErrorState';
import { Sheet } from '../../../components/ui/Sheet';
import { Skeleton } from '../../../components/ui/Skeleton';
import { StatusPill } from '../../../components/ui/StatusPill';
import { ApiError, api } from '../../../lib/api';
import { cn } from '../../../lib/cn';
import { formatFcfa } from '../../../lib/format';
import { useAsyncResource } from '../../../lib/useAsyncResource';
import type { Artisan, RequestEligibility, ServiceRequest } from '../../../types';
import { useMyRequests } from '../../requests/hooks/useMyRequests';

interface QuoteRequestSheetProps {
  artisan: Artisan;
  open: boolean;
  onClose: () => void;
  /** Explication affichée en tête (ex. ouvert depuis « Message »). */
  intro?: string | null;
}

/** Prénom affiché dans les libellés (« Envoyer à Idrissa »). */
function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' });
}

/** Lieu d'une demande, tel que le client l'a confirmé (demandes antérieures : position GPS). */
function placeOf(request: ServiceRequest): string {
  return request.locationLabel ?? 'position GPS enregistrée';
}

/**
 * Éligibilité de chaque demande ouverte pour CET artisan, telle que le
 * serveur la calcule (même règle que l'envoi) : le front ne devine jamais
 * une zone.
 */
function useRequestEligibility(artisanId: string) {
  const { data, isLoading, error, run, reload } = useAsyncResource<RequestEligibility[]>();
  useEffect(() => {
    run(() => api.listRequestEligibility(artisanId));
  }, [run, artisanId]);
  return { data, isLoading, error, reload };
}

/**
 * Contenu du panneau, monté seulement à l'ouverture (aucun appel réseau
 * avant que le client ne demande un devis).
 *
 * Règle du parcours (alignée sur le serveur, POST /interventions) : un
 * devis se demande à partir d'une demande décrite et OUVERTE, d'un métier
 * que l'artisan exerce, située DANS SA ZONE — l'artisan chiffre d'après la
 * description et le lieu. Une demande d'un autre métier n'est pas
 * proposée ; une demande hors de sa zone est montrée, marquée « Hors de sa
 * zone » et non sélectionnable, AVANT tout envoi (le serveur la refuserait
 * de toute façon : il reste le dernier rempart).
 */
const QuoteRequestContent: React.FC<{ artisan: Artisan }> = ({ artisan }) => {
  const { data: requests, isLoading, error, reload } = useMyRequests();
  const eligibility = useRequestEligibility(artisan.id);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const name = firstName(artisan.name);
  const openRequests = (requests ?? []).filter((request) => request.status === 'ouverte');
  const compatible = openRequests.filter((request) =>
    artisan.tradeCodes.includes(request.tradeCode),
  );
  const verdicts = new Map((eligibility.data ?? []).map((item) => [item.requestId, item] as const));
  const isEligible = (request: ServiceRequest) => verdicts.get(request.id)?.eligible === true;
  const sendable = compatible.filter(isEligible);
  // Sélection par défaut : la première demande envoyable, dans l'ordre
  // renvoyé par le serveur ; le client peut en choisir une autre.
  const selected: ServiceRequest | undefined =
    sendable.find((request) => request.id === selectedId) ?? sendable[0];

  const handleSend = async () => {
    if (!selected) return;
    setSendError(null);
    setIsSending(true);
    try {
      await api.createIntervention({ serviceRequestId: selected.id, artisanId: artisan.id });
      setSent(true);
    } catch (err) {
      setSendError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
    } finally {
      setIsSending(false);
    }
  };

  if (sent) {
    return (
      <div className="flex flex-col items-center text-center gap-4 py-2" role="status">
        <span
          aria-hidden
          className="inline-flex w-16 h-16 items-center justify-center rounded-full bg-success text-success-foreground"
        >
          <CheckCircle2 className="w-8 h-8" />
        </span>
        <div className="space-y-1">
          <p className="font-display text-title font-semibold text-foreground">
            Demande envoyée à {name}
          </p>
          <p className="text-sm text-muted-foreground">
            {name} va l&apos;étudier puis vous proposer un devis. Vous suivrez chaque étape dans «
            Devis et travaux ».
          </p>
        </div>
        <ButtonLink to="/mes-interventions" variant="brand" fullWidth>
          Suivre mes devis et travaux
        </ButtonLink>
      </div>
    );
  }

  if ((isLoading && requests === null) || (eligibility.isLoading && eligibility.data === null)) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  if (error && requests === null) {
    return <ErrorState message={error.message} onRetry={reload} />;
  }

  // Sans le verdict du serveur, rien n'est envoyable : on ne devine pas.
  if (eligibility.error && eligibility.data === null) {
    return <ErrorState message={eligibility.error.message} onRetry={eligibility.reload} />;
  }

  if (compatible.length === 0) {
    return (
      <div className="space-y-4">
        <Card tone="tint" className="flex items-start gap-3">
          <ClipboardList aria-hidden className="w-5 h-5 text-primary-emerald shrink-0 mt-0.5" />
          <p className="text-sm text-foreground">
            Pour chiffrer un devis, {name} s&apos;appuie sur la description de votre besoin et sur
            le lieu d&apos;intervention.{' '}
            {openRequests.length > 0
              ? 'Vos demandes ouvertes concernent un autre métier que le sien.'
              : "Vous n'avez pas encore de demande ouverte."}
          </p>
        </Card>
        <ButtonLink
          to={`/demande?artisan=${encodeURIComponent(artisan.id)}`}
          variant="primary"
          size="lg"
          fullWidth
        >
          Décrire mon besoin
        </ButtonLink>
        <p className="text-xs text-center text-muted-foreground">
          Votre demande sera ensuite envoyée directement à {name}.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <fieldset className="space-y-2">
        <legend className="text-sm font-semibold text-foreground mb-2">
          Quelle demande envoyer à {name} ?
        </legend>
        {compatible.map((request) => {
          const eligible = isEligible(request);
          const isSelected = eligible && request.id === selected?.id;
          const outOfZone = verdicts.get(request.id)?.reason === 'hors_zone';
          return (
            <label
              key={request.id}
              className={cn(
                'flex items-start gap-3 rounded-field p-3 transition-colors ring-1 ring-inset',
                !eligible
                  ? 'bg-surface-muted ring-border cursor-not-allowed'
                  : isSelected
                    ? 'bg-emerald-tint ring-primary-emerald cursor-pointer'
                    : 'bg-surface ring-border hover:bg-surface-muted cursor-pointer',
              )}
            >
              <input
                type="radio"
                name="demande-devis"
                value={request.id}
                checked={isSelected}
                disabled={!eligible}
                onChange={() => setSelectedId(request.id)}
                className="mt-1 w-4 h-4 accent-primary-emerald shrink-0"
              />
              <span className="min-w-0 flex-1 space-y-0.5">
                <span className="flex items-start justify-between gap-2">
                  <span className="text-sm font-semibold text-foreground">
                    {request.tradeLabel} · {formatDate(request.createdAt)}
                  </span>
                  {!eligible && (
                    <StatusPill tone="neutral">
                      {outOfZone ? 'Hors de sa zone' : 'Indisponible'}
                    </StatusPill>
                  )}
                </span>
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <MapPin aria-hidden className="w-3.5 h-3.5 shrink-0" />
                  Lieu : {placeOf(request)}
                </span>
                {!eligible && (
                  <span className="block text-xs text-foreground">
                    {outOfZone
                      ? `${name} n'intervient pas à ce lieu : cette demande ne peut pas lui être envoyée.`
                      : `Cette demande ne peut pas être envoyée à ${name}.`}
                  </span>
                )}
                <span className="block text-sm text-muted-foreground line-clamp-2">
                  {request.description}
                </span>
                {request.aiEstimateMinFcfa != null && request.aiEstimateMaxFcfa != null && (
                  <span className="block text-xs text-muted-foreground">
                    Estimation : {formatFcfa(request.aiEstimateMinFcfa)} –{' '}
                    {formatFcfa(request.aiEstimateMaxFcfa)}
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </fieldset>

      {sendError && (
        <p role="alert" className="text-sm text-destructive">
          {sendError}
        </p>
      )}

      {sendable.length === 0 ? (
        <div className="space-y-3">
          <Card tone="tint" className="text-sm text-foreground">
            Aucune de vos demandes n&apos;est dans la zone d&apos;intervention de {name}. Décrivez
            votre besoin en choisissant le lieu des travaux : nous vérifions qu&apos;il le couvre
            avant l&apos;envoi.
          </Card>
          <ButtonLink
            to={`/demande?artisan=${encodeURIComponent(artisan.id)}`}
            variant="primary"
            size="lg"
            fullWidth
          >
            Décrire mon besoin à un autre lieu
          </ButtonLink>
        </div>
      ) : (
        <Button
          variant="primary"
          size="lg"
          fullWidth
          isLoading={isSending}
          disabled={!selected}
          onClick={handleSend}
          leadingIcon={<Send aria-hidden className="w-5 h-5" />}
        >
          {isSending ? 'Envoi en cours...' : `Envoyer à ${name}`}
        </Button>
      )}
      <p className="text-xs text-center text-muted-foreground">
        Aucun numéro de téléphone n&apos;est partagé : tout se passe dans Téranga.
      </p>
    </div>
  );
};

/** « Demander un devis » depuis la fiche artisan (client connecté). */
export const QuoteRequestSheet: React.FC<QuoteRequestSheetProps> = ({
  artisan,
  open,
  onClose,
  intro,
}) => (
  <Sheet
    open={open}
    onClose={onClose}
    title="Demander un devis"
    description={`À ${artisan.name}, artisan vérifié.`}
  >
    {intro && (
      <p className="mb-4 rounded-field bg-emerald-tint px-3 py-2 text-sm text-foreground">
        {intro}
      </p>
    )}
    <QuoteRequestContent artisan={artisan} />
  </Sheet>
);
