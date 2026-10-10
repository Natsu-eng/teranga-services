import React, { useState } from 'react';
import { CheckCircle2, ClipboardList, Send } from 'lucide-react';
import { Button, ButtonLink } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { ErrorState } from '../../../components/ui/ErrorState';
import { Sheet } from '../../../components/ui/Sheet';
import { Skeleton } from '../../../components/ui/Skeleton';
import { ApiError, api } from '../../../lib/api';
import { cn } from '../../../lib/cn';
import { formatFcfa } from '../../../lib/format';
import type { Artisan, ServiceRequest } from '../../../types';
import { useMyRequests } from '../../requests/hooks/useMyRequests';

interface QuoteRequestSheetProps {
  artisan: Artisan;
  open: boolean;
  onClose: () => void;
}

/** Prénom affiché dans les libellés (« Envoyer à Idrissa »). */
function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' });
}

/**
 * Contenu du panneau, monté seulement à l'ouverture (aucun appel réseau
 * avant que le client ne demande un devis).
 *
 * Règle du parcours (alignée sur le serveur, POST /interventions) : un
 * devis se demande à partir d'une demande décrite et OUVERTE, d'un métier
 * que l'artisan exerce — l'artisan chiffre d'après la description et le
 * lieu. Les demandes incompatibles ne sont donc jamais proposées ; sans
 * demande compatible, on invite à décrire le besoin pour cet artisan.
 */
const QuoteRequestContent: React.FC<{ artisan: Artisan }> = ({ artisan }) => {
  const { data: requests, isLoading, error, reload } = useMyRequests();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const name = firstName(artisan.name);
  const openRequests = (requests ?? []).filter((request) => request.status === 'ouverte');
  const compatible = openRequests.filter((request) =>
    artisan.tradeCodes.includes(request.tradeCode),
  );
  // Sélection par défaut : la première demande compatible, dans l'ordre
  // renvoyé par le serveur ; le client peut en choisir une autre.
  const selected: ServiceRequest | undefined =
    compatible.find((request) => request.id === selectedId) ?? compatible[0];

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
            {name} va l&apos;étudier puis vous proposer un devis. Vous suivrez chaque étape dans vos
            interventions.
          </p>
        </div>
        <ButtonLink to="/mes-interventions" variant="brand" fullWidth>
          Suivre mes interventions
        </ButtonLink>
      </div>
    );
  }

  if (isLoading && requests === null) {
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
          const isSelected = request.id === selected?.id;
          return (
            <label
              key={request.id}
              className={cn(
                'flex items-start gap-3 rounded-field p-3 cursor-pointer transition-colors ring-1 ring-inset',
                isSelected
                  ? 'bg-emerald-tint ring-primary-emerald'
                  : 'bg-surface ring-border hover:bg-surface-muted',
              )}
            >
              <input
                type="radio"
                name="demande-devis"
                value={request.id}
                checked={isSelected}
                onChange={() => setSelectedId(request.id)}
                className="mt-1 w-4 h-4 accent-primary-emerald shrink-0"
              />
              <span className="min-w-0 space-y-0.5">
                <span className="block text-sm font-semibold text-foreground">
                  {request.tradeLabel} · {formatDate(request.createdAt)}
                </span>
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

      <Button
        variant="primary"
        size="lg"
        fullWidth
        isLoading={isSending}
        onClick={handleSend}
        leadingIcon={<Send aria-hidden className="w-5 h-5" />}
      >
        {isSending ? 'Envoi en cours...' : `Envoyer à ${name}`}
      </Button>
      <p className="text-xs text-center text-muted-foreground">
        Aucun numéro de téléphone n&apos;est partagé : tout se passe dans Téranga.
      </p>
    </div>
  );
};

/** « Demander un devis » depuis la fiche artisan (client connecté). */
export const QuoteRequestSheet: React.FC<QuoteRequestSheetProps> = ({ artisan, open, onClose }) => (
  <Sheet
    open={open}
    onClose={onClose}
    title="Demander un devis"
    description={`À ${artisan.name}, artisan vérifié.`}
  >
    <QuoteRequestContent artisan={artisan} />
  </Sheet>
);
