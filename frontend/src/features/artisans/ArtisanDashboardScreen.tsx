import React from 'react';
import { Briefcase, Clock, Star, Wallet } from 'lucide-react';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatFcfa } from '../../lib/format';
import { InterventionsList } from '../interventions/InterventionsList';
import { useCurrentUser } from '../profile/hooks/useCurrentUser';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { useArtisan } from './hooks/useArtisan';
import { useArtisanStats } from './hooks/useArtisanStats';
import { useAvailabilityToggle } from './hooks/useAvailabilityToggle';

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
}

const StatCard: React.FC<StatCardProps> = ({ icon, label, value }) => (
  <div className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle flex flex-col gap-1">
    <div className="text-primary">{icon}</div>
    <span className="font-bold text-lg text-primary leading-tight">{value}</span>
    <span className="text-[11px] font-sora text-muted-foreground-soft uppercase tracking-wider font-semibold">
      {label}
    </span>
  </div>
);

// The first screen where the client/artisan spaces must read as visibly
// distinct (AUDIT_PHASE2.md §3, §6): a dark `bg-primary` hero (vs. every
// client screen's light `bg-background`) carries the availability toggle,
// echoing the "Téranga Pro" identity already established in Header/BottomNav
// rather than inventing a new one.
export const ArtisanDashboardScreen: React.FC = () => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);
  const { data: currentUser, isLoading: isUserLoading } = useCurrentUser();
  const artisanId = currentUser?.artisanId ?? null;

  const {
    data: proArtisan,
    isLoading: isProfileLoading,
    error: profileError,
    reload: reloadProfile,
    setData: setProArtisan,
  } = useArtisan(role === 'artisan' ? artisanId : null);
  const {
    data: stats,
    isLoading: isStatsLoading,
    error: statsError,
    reload: reloadStats,
  } = useArtisanStats(role === 'artisan' ? artisanId : null);
  const { isSaving, error: toggleError, toggle } = useAvailabilityToggle();

  // A client landing on /pro (no route-level role guard exists today,
  // AUDIT_PHASE2.md §1) has no artisan_profile at all -- never the artisan
  // toggle/stats/actions, just an honest "not for you" message instead of
  // hooks stuck forever pending on a `null` id.
  if (role !== 'artisan') {
    return (
      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-6 pb-28">
        <EmptyState title="Cet espace est réservé aux artisans." />
      </main>
    );
  }

  if (!isUserLoading && !artisanId) {
    return (
      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-6 pb-28">
        <EmptyState title="Aucun profil artisan n'est associé à ce compte." />
      </main>
    );
  }

  const isAvailable = proArtisan?.available ?? false;

  const handleToggle = () => {
    if (!proArtisan) return;
    toggle(proArtisan.available, (next) =>
      setProArtisan((prev) => (prev ? { ...prev, available: next } : prev)),
    );
  };

  return (
    <main className="pb-28">
      <section className="bg-primary text-white px-4 md:px-8 pt-6 pb-8 rounded-b-3xl">
        <div className="max-w-3xl mx-auto space-y-4">
          <div>
            <p className="font-sora text-xs uppercase tracking-wider text-primary-emerald-foreground">
              Espace Pro
            </p>
            {isProfileLoading && !proArtisan ? (
              <div className="h-7 w-48 mt-1 rounded-xl bg-white/15 animate-pulse" />
            ) : (
              <h1 className="font-headline-md text-2xl font-bold">
                {proArtisan?.name ?? 'Mon activité'}
              </h1>
            )}
          </div>

          {proArtisan && (
            <div className="bg-white/10 rounded-2xl p-4 flex items-center justify-between gap-4 border border-white/10">
              <div className="flex items-center gap-3">
                <span
                  className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                    isAvailable ? 'bg-success' : 'bg-accent-soft'
                  }`}
                />
                <div>
                  <p
                    className={`font-sora text-sm font-bold px-2 py-0.5 rounded-full inline-block ${
                      isAvailable
                        ? 'bg-success text-success-foreground'
                        : 'bg-accent-soft text-accent-foreground-strong'
                    }`}
                  >
                    {isAvailable ? 'Disponible' : 'Indisponible'}
                  </p>
                  <p className="text-xs text-primary-emerald-foreground mt-1">
                    {isAvailable
                      ? 'Vous recevez de nouvelles demandes.'
                      : "Vous n'apparaissez plus dans les recherches."}
                  </p>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={isAvailable}
                aria-label="Basculer ma disponibilité"
                disabled={isSaving}
                onClick={handleToggle}
                className={`relative w-14 h-8 rounded-full transition-colors shrink-0 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed ${
                  isAvailable ? 'bg-success' : 'bg-white/25'
                }`}
              >
                <span
                  className={`absolute top-1 left-1 w-6 h-6 rounded-full bg-white shadow transition-transform ${
                    isAvailable ? 'translate-x-6' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          )}
          {toggleError && <p className="text-xs font-sora text-destructive-soft">{toggleError}</p>}
        </div>
      </section>

      <div className="max-w-3xl mx-auto px-4 md:px-8 pt-6 space-y-6">
        {profileError && !proArtisan && (
          <ErrorState message={profileError.message} onRetry={reloadProfile} />
        )}

        {isStatsLoading && !stats ? (
          <div className="grid grid-cols-2 gap-3">
            {[0, 1, 2, 3].map((key) => (
              <Skeleton key={key} className="h-24 rounded-2xl" />
            ))}
          </div>
        ) : statsError && !stats ? (
          <ErrorState message={statsError.message} onRetry={reloadStats} />
        ) : stats ? (
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              icon={<Wallet className="w-6 h-6" />}
              label="Revenus"
              value={stats.revenueFcfa != null ? formatFcfa(stats.revenueFcfa) : 'Non disponible'}
            />
            <StatCard
              icon={<Briefcase className="w-6 h-6" />}
              label="Interventions terminées"
              value={String(stats.interventionsCount)}
            />
            <StatCard
              icon={<Star className="w-6 h-6" />}
              label="Note moyenne"
              value={
                stats.ratingAvg != null
                  ? `${stats.ratingAvg.toFixed(1)} (${stats.reviewCount})`
                  : 'Pas encore noté'
              }
            />
            <StatCard
              icon={<Clock className="w-6 h-6" />}
              label="Taux de réponse"
              value={stats.responseRate != null ? `${Math.round(stats.responseRate * 100)}%` : 'Non communiqué'}
            />
          </div>
        ) : null}

        <section className="space-y-3">
          <h2 className="font-bold text-xl text-primary">Mes demandes</h2>
          <InterventionsList groupByStatus emptyTitle="Aucune demande pour le moment." />
        </section>
      </div>
    </main>
  );
};
