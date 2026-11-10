import React, { useEffect, useState } from 'react';
import { Banknote, Clock, Landmark, ShieldCheck, Wallet } from 'lucide-react';
import { AppBar } from '../../components/ui/AppBar';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatTile } from '../../components/ui/StatTile';
import { StatusPill } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { cn } from '../../lib/cn';
import { formatFcfa } from '../../lib/format';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { ArtisanEarnings, PayoutChannel, PayoutSettings } from '../../types';
import { MoneyBreakdown } from './components/MoneyBreakdown';
import { isOnlinePaymentActive, usePaymentOptions } from './hooks/usePaymentOptions';
import { CHANNEL_LABELS, paymentPill } from './paymentText';

/**
 * Où arrivent les versements : le moyen se choisit, le numéro jamais — c'est
 * celui du compte, vérifié par code SMS (un versement ne peut pas être
 * détourné vers un autre numéro).
 */
const PayoutSettingsCard: React.FC = () => {
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<PayoutSettings>();
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    run(() => api.getPayoutSettings());
  }, [run]);

  const choose = async (channel: PayoutChannel) => {
    setSaveError(null);
    setIsSaving(true);
    try {
      const updated = await api.updatePayoutSettings(channel);
      setData(() => updated);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Enregistrement impossible.');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading && !data) return <Skeleton className="h-36 rounded-card" />;
  if (error && !data) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;

  return (
    <Card className="space-y-3">
      <fieldset className="space-y-2" disabled={isSaving}>
        <legend className="text-sm font-semibold text-foreground mb-2">
          Recevoir mes versements sur
        </legend>
        {data.allowedChannels.map((channel) => {
          const isSelected = channel === data.channel;
          return (
            <label
              key={channel}
              className={cn(
                'flex items-center gap-3 rounded-field p-3 cursor-pointer transition-colors ring-1 ring-inset',
                isSelected
                  ? 'bg-emerald-tint ring-primary-emerald'
                  : 'bg-surface ring-border hover:bg-surface-muted',
              )}
            >
              <input
                type="radio"
                name="moyen-de-versement"
                value={channel}
                checked={isSelected}
                onChange={() => choose(channel)}
                className="w-4 h-4 accent-primary-emerald shrink-0"
              />
              <span className="text-sm font-semibold text-foreground">
                {CHANNEL_LABELS[channel]}
              </span>
            </label>
          );
        })}
      </fieldset>
      <p className="text-xs text-muted-foreground">
        Versements envoyés au numéro de votre compte, {data.destinationPhone}, vérifié par code SMS.
        Pour votre sécurité, il ne peut pas être remplacé par un autre numéro.
      </p>
      {saveError && (
        <p role="alert" className="text-sm text-destructive">
          {saveError}
        </p>
      )}
    </Card>
  );
};

/**
 * Gains de l'artisan (/pro/gains) : ce qu'il a encaissé et, pour chaque
 * intervention, le prix du devis, la commission Téranga (taux figé) et son
 * net — aucun montant ambigu.
 *
 * Suit la configuration RÉELLE (GET /payments/options) : en mode espèces,
 * seuls les espèces encaissées et la commission due sont montrées ; les
 * versements, le séquestre et le choix du moyen de versement n'apparaissent
 * que si le paiement en ligne est actif.
 */
export const EarningsScreen: React.FC = () => {
  const { data, isLoading, error, run, reload } = useAsyncResource<ArtisanEarnings>();
  const {
    data: options,
    isLoading: isOptionsLoading,
    error: optionsError,
    reload: reloadOptions,
  } = usePaymentOptions();
  const online = options !== null && isOnlinePaymentActive(options);

  useEffect(() => {
    run(() => api.getMyEarnings());
  }, [run]);

  return (
    <>
      <AppBar title="Mes gains" backTo="/pro" tone="pro" />
      <main className="w-full max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-10 space-y-7">
        {(isLoading && !data) || (isOptionsLoading && !options) ? (
          <div className="grid grid-cols-2 gap-3" aria-busy="true">
            {[0, 1, 2, 3].map((key) => (
              <Skeleton key={key} className="h-28 rounded-card" />
            ))}
          </div>
        ) : error && !data ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : optionsError && !options ? (
          <ErrorState message={optionsError.message} onRetry={reloadOptions} />
        ) : data && options ? (
          <>
            <section aria-label="Synthèse" className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                {online && (
                  <>
                    <StatTile
                      icon={<Wallet className="w-5 h-5" />}
                      label="Versé sur votre compte"
                      value={formatFcfa(data.totals.paidOutFcfa)}
                      hint={
                        data.totals.payoutPendingFcfa > 0
                          ? `+ ${formatFcfa(data.totals.payoutPendingFcfa)} en cours de versement`
                          : 'Net, commission déduite'
                      }
                    />
                    <StatTile
                      icon={<ShieldCheck className="w-5 h-5" />}
                      label="En séquestre"
                      value={formatFcfa(data.totals.inEscrowFcfa)}
                      hint="Net à recevoir à la fin des travaux"
                    />
                    <StatTile
                      icon={<Landmark className="w-5 h-5" />}
                      label="Commissions prélevées"
                      value={formatFcfa(data.totals.commissionCollectedFcfa)}
                      hint="Déduites de vos versements"
                    />
                  </>
                )}
                <StatTile
                  icon={<Banknote className="w-5 h-5" />}
                  label="Espèces encaissées"
                  value={formatFcfa(data.totals.cashReceivedFcfa)}
                  hint={
                    data.totals.commissionDueFcfa > 0
                      ? `Commission due : ${formatFcfa(data.totals.commissionDueFcfa)}`
                      : 'Aucune commission due'
                  }
                />
                {!online && (
                  <StatTile
                    icon={<Landmark className="w-5 h-5" />}
                    label="Commission due"
                    value={formatFcfa(data.totals.commissionDueFcfa)}
                    hint="Sur les travaux réglés en espèces"
                  />
                )}
              </div>
              {data.totals.commissionDueFcfa > 0 && (
                <Card tone="tint" padding="sm" className="flex items-start gap-2 text-sm">
                  <Clock aria-hidden className="w-4 h-4 shrink-0 mt-0.5 text-primary-emerald" />
                  <span>
                    Sur les travaux réglés en espèces ou hors de l&apos;application, la commission
                    de Téranga ({formatFcfa(data.totals.commissionDueFcfa)}) reste due.
                    {online && ' Les paiements en ligne la déduisent automatiquement.'}
                  </span>
                </Card>
              )}
            </section>

            <section aria-labelledby="historique-gains" className="space-y-3">
              <SectionHeader id="historique-gains" title="Détail par intervention" />
              {data.items.length === 0 ? (
                <EmptyState
                  title="Aucun paiement pour le moment."
                  description="Dès qu'un client paie un devis accepté, le détail apparaît ici : prix, commission et ce que vous touchez."
                />
              ) : (
                <ul className="space-y-3">
                  {data.items.map((item) => {
                    const pill = paymentPill(item.payment, 'artisan');
                    return (
                      <Card as="li" key={item.interventionId} className="space-y-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="font-semibold text-foreground">{item.tradeLabel}</p>
                            <p className="text-xs text-muted-foreground">
                              Client : {item.clientName}
                              {item.payment.channel
                                ? ` · ${CHANNEL_LABELS[item.payment.channel]}`
                                : ''}
                            </p>
                          </div>
                          <StatusPill tone={pill.tone}>{pill.label}</StatusPill>
                        </div>
                        <MoneyBreakdown payment={item.payment} role="artisan" />
                      </Card>
                    );
                  })}
                </ul>
              )}
            </section>
          </>
        ) : null}

        {/* Versements : seulement si le paiement en ligne existe (en espèces,
            l'artisan est payé de la main à la main, rien n'est versé). */}
        {online && (
          <section aria-labelledby="versements" className="space-y-3">
            <SectionHeader id="versements" title="Mes versements" />
            <PayoutSettingsCard />
          </section>
        )}
      </main>
    </>
  );
};
