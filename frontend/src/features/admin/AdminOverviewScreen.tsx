import React, { useEffect } from 'react';
import { Link } from 'react-router';
import { ChevronRight, RefreshCw } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatTile } from '../../components/ui/StatTile';
import { api } from '../../lib/api';
import { formatFcfa } from '../../lib/format';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { AdminOverview } from '../../types/admin';
import { formatAdminDateTime } from './adminText';

/** « 1 profil incomplet », « 3 profils incomplets ». */
const countLabel = (count: number, one: string, many: string) =>
  `${count} ${count > 1 ? many : one}`;

/** Une file de travail : son nombre, et le lien pour la traiter. */
const TodoRow: React.FC<{ to: string; label: string; count: number; empty: string }> = ({
  to,
  label,
  count,
  empty,
}) => (
  <li>
    <Link
      to={to}
      className="flex items-center justify-between gap-3 rounded-field px-3 py-3 hover:bg-emerald-tint"
    >
      <span className="min-w-0">
        <span className="block font-medium text-foreground">{label}</span>
        <span className="block text-sm text-muted-foreground">
          {count > 0 ? 'À traiter' : empty}
        </span>
      </span>
      <span className="flex items-center gap-2">
        <span
          className={
            count > 0
              ? 'font-display text-display-sm font-semibold text-accent-foreground-strong'
              : 'font-display text-display-sm font-semibold text-muted-foreground'
          }
        >
          {count}
        </span>
        <ChevronRight aria-hidden className="w-4 h-4 text-muted-foreground" />
      </span>
    </Link>
  </li>
);

const Section: React.FC<{ title: string; children: React.ReactNode; note?: string }> = ({
  title,
  children,
  note,
}) => (
  <section className="space-y-3" aria-label={title}>
    <h2 className="font-semibold text-foreground">{title}</h2>
    {children}
    {note && <p className="text-xs text-muted-foreground">{note}</p>}
  </section>
);

function isEmpty(overview: AdminOverview): boolean {
  const interventions = Object.values(overview.interventions).reduce((a, b) => a + b, 0);
  return interventions === 0 && overview.artisans.total === 0 && overview.users.clients === 0;
}

/**
 * Vue d'ensemble (/admin) : ce qui attend une décision, puis l'état de la
 * plateforme. Chaque chiffre vient du serveur, dérivé des tables métier ;
 * sans activité, des zéros honnêtes, jamais un chiffre inventé.
 */
export const AdminOverviewScreen: React.FC = () => {
  const { data, isLoading, error, run, reload } = useAsyncResource<AdminOverview>();

  useEffect(() => {
    run(() => api.getAdminOverview());
  }, [run]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="font-display text-display-md font-semibold text-primary">
            Vue d’ensemble
          </h1>
          <p className="text-sm text-muted-foreground">
            {data
              ? `Chiffres calculés le ${formatAdminDateTime(data.generatedAt)}.`
              : 'Chiffres calculés à partir des données réelles de la plateforme.'}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={reload}
          disabled={isLoading}
          leadingIcon={<RefreshCw aria-hidden className="w-4 h-4" />}
        >
          Actualiser
        </Button>
      </div>

      {isLoading && !data ? (
        <div className="space-y-4" aria-busy="true">
          <Skeleton className="h-40 rounded-card" />
          <Skeleton className="h-28 rounded-card" />
        </div>
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data ? (
        <>
          <Card as="section" padding="md" aria-label="À traiter">
            <h2 className="px-3 pb-1 font-semibold text-foreground">À traiter</h2>
            <ul className="divide-y divide-border">
              <TodoRow
                to="/admin/verifications"
                label="Documents à vérifier"
                count={data.pendingVerifications}
                empty="Aucun document en attente"
              />
              <TodoRow
                to="/admin/litiges"
                label="Litiges à trancher"
                count={data.openDisputes}
                empty="Aucun litige ouvert"
              />
              <TodoRow
                to="/admin/avis"
                label="Avis signalés"
                count={data.reportedReviews}
                empty="Aucun avis signalé"
              />
            </ul>
          </Card>

          {isEmpty(data) && (
            <p className="rounded-field bg-surface-muted p-3 text-sm text-muted-foreground">
              Aucune activité pour l’instant : les chiffres ci-dessous se rempliront avec les
              premières inscriptions et interventions.
            </p>
          )}

          <Section title="Artisans">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatTile
                label="Inscrits"
                value={data.artisans.total}
                hint={countLabel(data.artisans.none, 'profil incomplet', 'profils incomplets')}
              />
              <StatTile label="Vérifiés" value={data.artisans.verified} />
              <StatTile
                label="En attente"
                value={data.artisans.pending}
                hint={countLabel(data.artisans.rejected, 'refusé', 'refusés')}
              />
              <StatTile label="Suspendus" value={data.artisans.suspended} />
              <StatTile
                label="Vérifiés non placés"
                value={data.artisans.verifiedUnplaced}
                hint="Ne reçoivent aucune demande"
              />
            </div>
          </Section>

          <Section title="Comptes">
            <div className="grid grid-cols-3 gap-3">
              <StatTile label="Clients" value={data.users.clients} />
              <StatTile label="Artisans" value={data.users.artisans} />
              <StatTile label="Admins" value={data.users.admins} />
            </div>
          </Section>

          <Section title="Interventions">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <StatTile label="Proposées" value={data.interventions.proposee} />
              <StatTile label="Acceptées" value={data.interventions.acceptee} />
              <StatTile label="En cours" value={data.interventions.enCours} />
              <StatTile label="Terminées" value={data.interventions.terminee} />
              <StatTile label="Annulées" value={data.interventions.annulee} />
              <StatTile label="En litige" value={data.interventions.litige} />
            </div>
          </Section>

          <Section
            title="Argent"
            note="Volume d’affaires = séquestre + versé aux artisans + espèces (remboursements exclus)."
          >
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <StatTile
                label="Volume d’affaires"
                value={formatFcfa(data.money.businessVolumeFcfa)}
              />
              <StatTile
                label="En séquestre"
                value={formatFcfa(data.money.inEscrowFcfa)}
                hint="En attente de la fin des travaux"
              />
              <StatTile label="Versé aux artisans" value={formatFcfa(data.money.releasedFcfa)} />
              <StatTile label="Espèces" value={formatFcfa(data.money.cashFcfa)} />
              <StatTile label="Remboursé" value={formatFcfa(data.money.refundedFcfa)} />
            </div>
          </Section>

          <Section
            title="Commissions"
            note="Toujours calculées sur le taux figé de chaque intervention."
          >
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <StatTile
                label="Collectées"
                value={formatFcfa(data.money.commissionCollectedFcfa)}
                hint="Prélevées à la libération du séquestre"
              />
              <StatTile
                label="Dues par les artisans"
                value={formatFcfa(data.money.commissionDueFcfa)}
                hint="Travaux terminés réglés en espèces"
              />
              <StatTile
                label="À prélever"
                value={formatFcfa(data.money.commissionPendingFcfa)}
                hint="Travaux en cours, prélevées à la libération"
              />
            </div>
          </Section>
        </>
      ) : null}
    </div>
  );
};
