import React, { useEffect, useState } from 'react';
import { Banknote, CheckCircle2, Clock, CreditCard, ShieldCheck } from 'lucide-react';
import { useParams, useSearchParams } from 'react-router';
import { AppBar } from '../../components/ui/AppBar';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { ApiError, api } from '../../lib/api';
import { cn } from '../../lib/cn';
import { navigateToExternal } from '../../lib/externalNavigation';
import { formatFcfa } from '../../lib/format';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type {
  Intervention,
  PaymentChannel,
  PaymentOptions,
  PaymentStatus,
  PaymentSummary,
} from '../../types';
import { MoneyBreakdown } from './components/MoneyBreakdown';
import { CHANNEL_LABELS, canStartPayment, formatPaymentDate } from './paymentText';

/*
 * Au retour du fournisseur, sa notification (webhook) peut arriver un peu
 * après le navigateur : l'écran relit l'état toutes les 3 s, pendant au
 * plus 2 min (40 relectures). Au-delà, le paiement sera pris en compte à
 * réception — l'écran le dit au lieu de tourner sans fin.
 */
export const CONFIRMATION_POLL_MS = 3_000;
export const CONFIRMATION_MAX_POLLS = 40;

const CHANNEL_MARKS: Record<PaymentChannel, { mark: React.ReactNode; className: string }> = {
  wave: { mark: 'W', className: 'bg-brand-wave text-foreground' },
  orange_money: { mark: 'OM', className: 'bg-brand-orange-money text-foreground' },
  free_money: { mark: 'FM', className: 'bg-surface-muted text-foreground' },
  carte: {
    mark: <CreditCard className="w-4 h-4" />,
    className: 'bg-emerald-tint text-primary-emerald',
  },
  cash: { mark: <Banknote className="w-4 h-4" />, className: 'bg-accent-soft text-primary' },
};

interface PaymentData {
  intervention: Intervention;
  options: PaymentOptions;
}

/** Écran neutre pour un paiement introuvable ou indisponible. */
const Unavailable: React.FC<{ title: string; description?: string }> = ({ title, description }) => (
  <EmptyState title={title} description={description}>
    <ButtonLink to="/mes-interventions" variant="outline" size="sm">
      Voir mes devis et travaux
    </ButtonLink>
  </EmptyState>
);

/** Paiement abouti (ou réglé autrement) : ce qui se passe maintenant, en clair. */
const PaymentDone: React.FC<{
  payment: PaymentSummary;
  canSwitchToOnline: boolean;
  onSwitchToOnline: () => void;
}> = ({ payment, canSwitchToOnline, onSwitchToOnline }) => {
  const amount = formatFcfa(payment.amountFcfa);
  const messages: Partial<Record<PaymentStatus, { title: string; text: string }>> = {
    retenu: {
      title: 'Paiement reçu',
      text: `${amount} sont conservés par Téranga. Ils ne seront versés à l'artisan que lorsque vous confirmerez la fin des travaux. En cas de problème, signalez-le depuis le suivi : vous serez remboursé si les travaux ne sont pas réalisés.`,
    },
    reussi: {
      title: 'Paiement en espèces enregistré',
      text: `Vous réglerez ${amount} directement à l'artisan. Ce règlement n'est pas protégé par le séquestre de Téranga ; vous pouvez encore choisir de payer en ligne tant que les travaux sont en cours.`,
    },
    libere: {
      title: "Versé à l'artisan",
      text: payment.releasedAt
        ? `Paiement versé à l'artisan le ${formatPaymentDate(payment.releasedAt)}.`
        : "Paiement versé à l'artisan.",
    },
    rembourse: {
      title: 'Paiement remboursé',
      text: `${amount} vous ont été remboursés.`,
    },
  };
  const message = (payment.status && messages[payment.status]) || {
    title: 'Paiement enregistré',
    text: '',
  };
  return (
    <Card padding="lg" className="space-y-4 text-center">
      <CheckCircle2 aria-hidden className="w-12 h-12 mx-auto text-primary-emerald" />
      <h2 className="font-display text-title font-semibold text-foreground">{message.title}</h2>
      <p className="text-sm text-muted-foreground">{message.text}</p>
      <ButtonLink to="/mes-interventions" variant="brand" fullWidth>
        Suivre mes travaux
      </ButtonLink>
      {canSwitchToOnline && (
        <Button variant="ghost" fullWidth onClick={onSwitchToOnline}>
          Payer en ligne plutôt
        </Button>
      )}
    </Card>
  );
};

/**
 * Paiement d'une intervention par le client (/paiement/:interventionId),
 * après acceptation du devis.
 *
 * Transparence : le total payé est celui du devis, sans frais ajoutés ;
 * l'écran explique le séquestre (argent conservé par Téranga jusqu'à la
 * confirmation de fin des travaux) et ce que change le choix des espèces.
 * Le montant n'est JAMAIS envoyé par le front : le serveur le fixe.
 */
export const PaymentScreen: React.FC = () => {
  const { interventionId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const returnedFrom = searchParams.get('retour');
  const { data, isLoading, error, run, reload } = useAsyncResource<PaymentData>();
  const [selected, setSelected] = useState<PaymentChannel | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [polls, setPolls] = useState(0);
  // Espèces déclarées : le client peut encore préférer le paiement protégé.
  const [switchToOnline, setSwitchToOnline] = useState(false);

  useEffect(() => {
    run(async () => {
      const [intervention, options] = await Promise.all([
        api.getInterventionById(interventionId),
        api.getPaymentOptions(),
      ]);
      return { intervention, options };
    });
  }, [run, interventionId]);

  const payment = data?.intervention.payment ?? null;
  const awaitingConfirmation = returnedFrom === 'succes' && payment?.status === 'en_attente';

  // Retour du fournisseur : relecture jusqu'à la confirmation (bornée).
  useEffect(() => {
    if (!awaitingConfirmation || polls >= CONFIRMATION_MAX_POLLS) return;
    const timer = setTimeout(() => {
      setPolls((count) => count + 1);
      reload();
    }, CONFIRMATION_POLL_MS);
    return () => clearTimeout(timer);
  }, [awaitingConfirmation, polls, reload]);

  const channels: PaymentChannel[] = data
    ? [
        ...data.options.onlineChannels,
        ...(data.options.cashEnabled && !switchToOnline ? (['cash'] as const) : []),
      ]
    : [];
  // Choix par défaut : le premier moyen en ligne (protégé par le séquestre).
  const channel = selected ?? channels[0] ?? null;

  const handlePay = async () => {
    if (!channel || !data) return;
    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const result = await api.initPayment(data.intervention.id, channel);
      if (channel === 'cash') {
        reload();
        return;
      }
      if (!result.checkoutUrl) {
        throw new ApiError('unknown', "La page de paiement n'a pas pu être ouverte.");
      }
      navigateToExternal(result.checkoutUrl);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : 'Le paiement n’a pas pu démarrer. Réessayez.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  let content: React.ReactNode;
  if (isLoading && !data) {
    content = (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-32 rounded-card" />
        <Skeleton className="h-56 rounded-card" />
      </div>
    );
  } else if (error && !data) {
    content =
      error.code === 'forbidden' || error.code === 'not_found' ? (
        <Unavailable title="Ce paiement est introuvable." />
      ) : (
        <ErrorState message={error.message} onRetry={reload} />
      );
  } else if (!data || !payment) {
    content = (
      <Unavailable
        title="Rien à payer pour le moment."
        description="Le paiement s'ouvre une fois le devis de l'artisan accepté."
      />
    );
  } else if (
    payment.status === 'retenu' ||
    payment.status === 'libere' ||
    payment.status === 'rembourse' ||
    (payment.status === 'reussi' && !switchToOnline)
  ) {
    content = (
      <PaymentDone
        payment={payment}
        canSwitchToOnline={
          payment.status === 'reussi' &&
          data.intervention.status === 'en_cours' &&
          data.options.onlineChannels.length > 0
        }
        onSwitchToOnline={() => {
          setSelected(null);
          setSwitchToOnline(true);
        }}
      />
    );
  } else if (awaitingConfirmation) {
    content = (
      <Card padding="lg" className="space-y-3 text-center" role="status">
        <Clock aria-hidden className="w-10 h-10 mx-auto text-primary-emerald" />
        <h2 className="font-display text-title font-semibold text-foreground">
          Confirmation du paiement…
        </h2>
        <p className="text-sm text-muted-foreground">
          {polls >= CONFIRMATION_MAX_POLLS
            ? 'La confirmation tarde. Votre paiement sera pris en compte dès que le service de paiement nous l’aura confirmé : vous pouvez quitter cette page sans risque.'
            : 'Nous attendons la confirmation du service de paiement. Cela prend en général quelques secondes.'}
        </p>
        <ButtonLink to="/mes-interventions" variant="ghost" size="sm">
          Suivre mes travaux
        </ButtonLink>
      </Card>
    );
  } else if (data.intervention.status !== 'en_cours' || !canStartPayment(payment)) {
    content = (
      <Unavailable
        title="Ce paiement n'est plus disponible."
        description="L'intervention n'est plus en cours."
      />
    );
  } else {
    const quote = data.intervention.quote;
    content = (
      <div className="space-y-5">
        {returnedFrom === 'echec' && (
          <p
            role="alert"
            className="rounded-field bg-destructive-soft p-3 text-sm text-destructive"
          >
            Le paiement n&apos;a pas abouti : aucun montant n&apos;a été prélevé. Vous pouvez
            réessayer, avec le même moyen ou un autre.
          </p>
        )}

        <Card className="space-y-3">
          <h2 className="font-semibold text-foreground">
            {data.intervention.serviceRequest.tradeLabel}
          </h2>
          {quote && (
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Main d&apos;œuvre</dt>
              <dd className="text-right text-foreground">{formatFcfa(quote.laborFcfa)}</dd>
              <dt className="text-muted-foreground">Matériaux</dt>
              <dd className="text-right text-foreground">{formatFcfa(quote.materialsFcfa)}</dd>
            </dl>
          )}
          <MoneyBreakdown payment={payment} role="client" />
        </Card>

        <Card tone="tint" padding="sm" className="flex items-start gap-2 text-sm">
          <ShieldCheck aria-hidden className="w-4 h-4 shrink-0 mt-0.5 text-primary-emerald" />
          <span>
            Paiement en ligne protégé : Téranga conserve votre argent et ne le verse à
            l&apos;artisan qu&apos;après votre confirmation de fin des travaux. En cas de problème,
            vous êtes remboursé si les travaux ne sont pas réalisés.
          </span>
        </Card>

        {channels.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Aucun moyen de paiement n&apos;est disponible pour le moment.
          </p>
        ) : (
          <fieldset className="space-y-2">
            <legend className="text-sm font-semibold text-foreground mb-2">
              Comment souhaitez-vous payer ?
            </legend>
            {channels.map((option) => {
              const isSelected = option === channel;
              const mark = CHANNEL_MARKS[option];
              return (
                <label
                  key={option}
                  className={cn(
                    'flex items-center gap-3 rounded-field p-3 cursor-pointer transition-colors ring-1 ring-inset',
                    isSelected
                      ? 'bg-emerald-tint ring-primary-emerald'
                      : 'bg-surface ring-border hover:bg-surface-muted',
                  )}
                >
                  <input
                    type="radio"
                    name="moyen-de-paiement"
                    value={option}
                    checked={isSelected}
                    onChange={() => setSelected(option)}
                    className="w-4 h-4 accent-primary-emerald shrink-0"
                  />
                  <span
                    aria-hidden
                    className={cn(
                      'inline-flex w-8 h-8 shrink-0 items-center justify-center rounded-full text-xs font-bold',
                      mark.className,
                    )}
                  >
                    {mark.mark}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-foreground">
                      {CHANNEL_LABELS[option]}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {option === 'cash'
                        ? "Vous réglez l'artisan en main propre — sans protection du séquestre."
                        : 'Paiement sécurisé, conservé par Téranga jusqu’à la fin des travaux.'}
                    </span>
                  </span>
                </label>
              );
            })}
          </fieldset>
        )}

        {submitError && (
          <p role="alert" className="text-sm text-destructive">
            {submitError}
          </p>
        )}

        {channel && (
          <Button
            variant="primary"
            size="lg"
            fullWidth
            isLoading={isSubmitting}
            onClick={handlePay}
            leadingIcon={<ShieldCheck aria-hidden className="w-5 h-5" />}
          >
            {channel === 'cash'
              ? `Je paierai ${formatFcfa(payment.amountFcfa)} en espèces`
              : `Payer ${formatFcfa(payment.amountFcfa)} avec ${CHANNEL_LABELS[channel]}`}
          </Button>
        )}
      </div>
    );
  }

  return (
    <>
      <AppBar title="Paiement" backTo="/mes-interventions" />
      <main className="w-full max-w-xl mx-auto px-4 md:px-8 pt-4 pb-10">{content}</main>
    </>
  );
};
