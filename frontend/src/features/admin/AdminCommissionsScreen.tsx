import React, { useEffect, useMemo, useState } from 'react';
import { Lock, Percent } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SelectField, TextField } from '../../components/ui/Field';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { Trade } from '../../types';
import type { CommissionGrid, CommissionRate } from '../../types/admin';
import { formatRate } from '../payments/paymentText';
import { RATE_STATE, formatAdminDateTime, percentToBps } from './adminText';
import { ConfirmActionSheet } from './components/ConfirmActionSheet';

const scopeLabel = (rate: Pick<CommissionRate, 'tradeLabel'>) =>
  rate.tradeLabel ?? 'Tous métiers (taux global)';

const RateRow: React.FC<{ rate: CommissionRate }> = ({ rate }) => (
  <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
    <div className="min-w-0 space-y-0.5">
      <p className="font-medium text-foreground">
        {formatRate(rate.rateBps)} · {scopeLabel(rate)}
      </p>
      <p className="text-sm text-muted-foreground">
        Du {formatAdminDateTime(rate.effectiveFrom)}
        {rate.effectiveTo ? ` au ${formatAdminDateTime(rate.effectiveTo)}` : ', sans date de fin'}
      </p>
      <p className="text-xs text-muted-foreground">
        {rate.interventionsCount === 0
          ? 'Aucune intervention n’a figé ce taux.'
          : `${rate.interventionsCount} intervention${
              rate.interventionsCount > 1 ? 's ont' : ' a'
            } figé ce taux.`}
      </p>
    </div>
    <StatusPill tone={RATE_STATE[rate.state].tone}>{RATE_STATE[rate.state].label}</StatusPill>
  </li>
);

/**
 * Grille de commission (/admin/commissions). On AJOUTE un taux daté ; on ne
 * modifie ni ne supprime jamais un taux. Chaque intervention a figé le taux
 * en vigueur à sa création : un nouveau taux ne s'applique qu'aux
 * interventions créées après sa date d'effet.
 */
export const AdminCommissionsScreen: React.FC = () => {
  const grid = useAsyncResource<CommissionGrid>();
  const trades = useAsyncResource<Trade[]>();
  const [percent, setPercent] = useState('');
  const [tradeCode, setTradeCode] = useState('');
  const [when, setWhen] = useState<'now' | 'later'>('now');
  const [startsAt, setStartsAt] = useState('');
  // Vérifiée à la saisie (le serveur revérifie à l'envoi : DATE_EFFET_PASSEE).
  const [dateError, setDateError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const runGrid = grid.run;
  const runTrades = trades.run;

  useEffect(() => {
    runGrid(() => api.getCommissionGrid());
    runTrades(() => api.listTrades());
  }, [runGrid, runTrades]);

  const bps = percentToBps(percent);
  const maxBps = grid.data?.maxRateBps ?? 0;
  const startDate = when === 'later' && startsAt ? new Date(startsAt) : null;
  const percentError =
    percent && bps === null
      ? 'Saisissez un pourcentage, par exemple 10 ou 7,5.'
      : bps !== null && bps > maxBps
        ? `Le plafond de saisie est de ${formatRate(maxBps)}.`
        : null;
  const canSubmit =
    bps !== null && !percentError && (when === 'now' || (startDate !== null && !dateError));

  // Taux de même portée en vigueur aujourd'hui : il se terminera où le nouveau commence.
  const current = useMemo(
    () =>
      grid.data?.items.find(
        (rate) => rate.state === 'en_vigueur' && (rate.tradeCode ?? '') === tradeCode,
      ) ?? null,
    [grid.data, tradeCode],
  );
  const tradeName = tradeCode
    ? (trades.data?.find((trade) => trade.code === tradeCode)?.labelFr ?? tradeCode)
    : 'tous les métiers sans taux propre';

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-display-md font-semibold text-primary">Commissions</h1>
        <p className="text-sm text-muted-foreground">Grille des taux, versionnée et datée.</p>
      </div>

      <Card as="aside" padding="md" className="flex gap-3 text-sm">
        <Lock aria-hidden className="w-5 h-5 shrink-0 text-primary" />
        <div className="space-y-1 text-muted-foreground">
          <p className="font-semibold text-foreground">Les taux passés ne bougent jamais</p>
          <p>
            Chaque intervention fige le taux en vigueur à sa création : sa commission est toujours
            calculée sur ce taux, même après un changement de grille. Un nouveau taux ne concerne
            que les interventions créées après sa date d’effet.
          </p>
          <p>
            On ajoute un taux, on ne le modifie ni ne le supprime. Un taux propre à un métier prime
            sur le taux global.
          </p>
        </div>
      </Card>

      <Card as="section" padding="lg" className="space-y-4" aria-label="Ajouter un taux">
        <h2 className="font-semibold text-foreground">Ajouter un taux</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <TextField
            label="Taux (%)"
            inputMode="decimal"
            placeholder="10"
            value={percent}
            onChange={(event) => setPercent(event.target.value)}
            error={percentError}
            hint={grid.data ? `Plafond de saisie : ${formatRate(maxBps)}.` : undefined}
          />
          <SelectField
            label="Portée"
            value={tradeCode}
            onChange={(event) => setTradeCode(event.target.value)}
          >
            <option value="">Tous métiers (taux global)</option>
            {(trades.data ?? []).map((trade) => (
              <option key={trade.code} value={trade.code}>
                {trade.labelFr}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Date d’effet"
            value={when}
            onChange={(event) => setWhen(event.target.value as 'now' | 'later')}
          >
            <option value="now">Immédiatement</option>
            <option value="later">À une date future</option>
          </SelectField>
          {when === 'later' && (
            <TextField
              label="À partir du"
              type="datetime-local"
              value={startsAt}
              onChange={(event) => {
                const value = event.target.value;
                setStartsAt(value);
                setDateError(
                  value && new Date(value).getTime() <= new Date().getTime()
                    ? 'La date d’effet doit être dans le futur.'
                    : null,
                );
              }}
              error={dateError}
            />
          )}
        </div>
        {notice && (
          <p role="status" className="rounded-field bg-emerald-tint p-3 text-sm text-primary">
            {notice}
          </p>
        )}
        <Button
          variant="brand"
          disabled={!canSubmit || !grid.data}
          onClick={() => {
            setNotice(null);
            setConfirming(true);
          }}
        >
          Vérifier et ajouter
        </Button>
      </Card>

      <section className="space-y-3" aria-label="Grille actuelle">
        <h2 className="font-semibold text-foreground">Grille</h2>
        {grid.isLoading && !grid.data ? (
          <Skeleton className="h-48 rounded-card" />
        ) : grid.error && !grid.data ? (
          <ErrorState message={grid.error.message} onRetry={grid.reload} />
        ) : grid.data && grid.data.items.length === 0 ? (
          <EmptyState
            icon={<Percent />}
            title="Aucun taux configuré."
            description="Sans taux en vigueur, aucune intervention ne peut être créée."
          />
        ) : grid.data ? (
          <Card padding="none" className="overflow-hidden">
            <ul className="divide-y divide-border">
              {grid.data.items.map((rate) => (
                <RateRow key={rate.id} rate={rate} />
              ))}
            </ul>
          </Card>
        ) : null}
      </section>

      <ConfirmActionSheet
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Ajouter ce taux"
        confirmLabel="Ajouter le taux"
        effect={
          <ul className="list-disc pl-5 space-y-1">
            <li>
              <strong>{bps !== null ? formatRate(bps) : '—'}</strong> pour {tradeName},{' '}
              {startDate
                ? `à partir du ${formatAdminDateTime(startDate.toISOString())}`
                : 'dès maintenant'}
              .
            </li>
            {current ? (
              <li>
                Le taux actuel ({formatRate(current.rateBps)}) se terminera à cette date ; ses{' '}
                {current.interventionsCount} intervention
                {current.interventionsCount > 1 ? 's' : ''} garde
                {current.interventionsCount > 1 ? 'nt' : ''} leur taux.
              </li>
            ) : (
              <li>
                {tradeCode
                  ? 'Ce métier suivait le taux global ; il aura désormais son propre taux.'
                  : 'Aucun taux global n’est en vigueur actuellement.'}
              </li>
            )}
            <li>Ce taux ne pourra être ni modifié ni supprimé, seulement remplacé.</li>
          </ul>
        }
        reason={{ label: 'Note', mode: 'optional' }}
        onConfirm={async (note) => {
          if (bps === null) return;
          const created = await api.addCommissionRate({
            rateBps: bps,
            tradeCode: tradeCode || null,
            effectiveFrom: startDate ? startDate.toISOString() : null,
            note,
          });
          setPercent('');
          setStartsAt('');
          setWhen('now');
          setNotice(`Taux de ${formatRate(created.rateBps)} ajouté pour ${scopeLabel(created)}.`);
          grid.reload();
        }}
      />
    </div>
  );
};
