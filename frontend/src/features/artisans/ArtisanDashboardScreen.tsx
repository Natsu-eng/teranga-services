import React from 'react';
import { Ban, Briefcase, ClipboardCheck, Clock, Star, Wallet } from 'lucide-react';
import { useNavigate } from 'react-router';
import { RoleRestricted } from '../../components/auth/RoleRestricted';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatTile } from '../../components/ui/StatTile';
import { Switch } from '../../components/ui/Switch';
import { formatFcfa } from '../../lib/format';
import { greetingLine } from '../../lib/greeting';
import { firstNameOf } from '../../lib/identity';
import { InterventionsList } from '../interventions/InterventionsList';
import { useCurrentUser } from '../profile/hooks/useCurrentUser';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { MyReviewsSection } from './MyReviewsSection';
import { VerificationStatusBanner } from './VerificationStatusBanner';
import { useArtisanStats } from './hooks/useArtisanStats';
import { useAvailabilityToggle } from './hooks/useAvailabilityToggle';
import { useMyArtisanProfile } from './hooks/useMyArtisanProfile';

/** Note au format français (4.8 -> « 4,8 »). */
function formatRating(value: number): string {
  return value.toFixed(1).replace('.', ',');
}

/**
 * Tableau de bord de l'espace Pro (/pro).
 *
 * Signature visuelle de l'espace artisan : le BANDEAU vert profond de
 * l'en-tête se prolonge ici (salutation, disponibilité), puis les
 * indicateurs chevauchent son bas arrondi. Mêmes composants que l'espace
 * client (cartes, tuiles, pastilles), identité nettement distincte.
 *
 * Un artisan non vérifié ne voit ni statistiques ni demandes (toujours
 * vides, aucune mise en relation possible avant vérification) mais l'état
 * de son onboarding : jamais les deux mélangés.
 */
export const ArtisanDashboardScreen: React.FC = () => {
  const navigate = useNavigate();
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
  } = useMyArtisanProfile(role === 'artisan' ? artisanId : null);
  const isVerified = proArtisan?.verifiedStatus === 'verified';
  // Statistiques demandées seulement pour un artisan vérifié : appel réseau
  // évité, pas seulement masqué.
  const {
    data: stats,
    isLoading: isStatsLoading,
    error: statsError,
    reload: reloadStats,
  } = useArtisanStats(role === 'artisan' && isVerified ? artisanId : null);
  const { isSaving, error: toggleError, toggle } = useAvailabilityToggle();

  // Défense en profondeur : la route est déjà réservée aux artisans
  // (ProtectedRoute roles=['artisan']) ; l'écran ne s'affiche jamais pour
  // un autre rôle même monté directement.
  if (role !== 'artisan') {
    return <RoleRestricted reservedFor="artisan" currentRole={auth.role} />;
  }

  if (!isUserLoading && !artisanId) {
    return (
      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-6">
        <EmptyState title="Aucun profil artisan n'est associé à ce compte." />
      </main>
    );
  }

  const isAvailable = proArtisan?.isAvailable ?? false;
  const greetingName = firstNameOf(proArtisan?.fullName);

  const handleToggle = () => {
    if (!proArtisan) return;
    toggle(proArtisan.isAvailable, (next) =>
      setProArtisan((prev) => (prev ? { ...prev, isAvailable: next } : prev)),
    );
  };

  return (
    <main>
      <section
        data-tone="dark"
        className="bg-primary text-white px-4 md:px-8 pt-2 pb-16 rounded-b-sheet"
      >
        <div className="max-w-3xl mx-auto space-y-5">
          <div className="space-y-1">
            <p className="text-caption font-semibold uppercase tracking-[0.14em] text-accent">
              Espace Pro
            </p>
            {isProfileLoading && !proArtisan ? (
              <div className="h-8 w-48 rounded-field bg-white/15 animate-pulse" />
            ) : (
              <h1 className="font-display text-display-md font-semibold">
                {greetingName ? greetingLine(greetingName) : 'Mon activité'}
              </h1>
            )}
          </div>

          {proArtisan && (
            <div className="rounded-card bg-white/10 p-4 flex items-center justify-between gap-4">
              <div className="min-w-0 space-y-0.5">
                <p className="flex items-center gap-2 font-semibold">
                  <span
                    aria-hidden
                    className={
                      isAvailable
                        ? 'w-2.5 h-2.5 rounded-full bg-primary-emerald-foreground'
                        : 'w-2.5 h-2.5 rounded-full bg-accent'
                    }
                  />
                  {isAvailable ? 'Disponible' : 'Indisponible'}
                </p>
                <p className="text-sm text-primary-emerald-foreground">
                  {isAvailable
                    ? 'Vous recevez de nouvelles demandes.'
                    : "Vous n'apparaissez plus dans les recherches."}
                </p>
              </div>
              <Switch
                checked={isAvailable}
                onChange={handleToggle}
                label="Basculer ma disponibilité"
                disabled={isSaving}
                tone="on-dark"
              />
            </div>
          )}
          {toggleError && (
            <p role="alert" className="text-sm text-destructive-soft">
              {toggleError}
            </p>
          )}
        </div>
      </section>

      <div className="max-w-3xl mx-auto px-4 md:px-8 -mt-10 space-y-7">
        {profileError && !proArtisan && (
          <ErrorState message={profileError.message} onRetry={reloadProfile} />
        )}

        {proArtisan?.isSuspended && (
          <Card as="aside" padding="lg" role="status" className="space-y-2 bg-destructive-soft">
            <p className="flex items-center gap-2 font-semibold text-destructive">
              <Ban aria-hidden className="w-5 h-5" />
              Compte suspendu par l’équipe Téranga
            </p>
            <p className="text-sm text-foreground">
              Votre profil n’apparaît plus dans la recherche et vous ne recevez plus de nouvelles
              demandes. Vos interventions en cours continuent normalement.
            </p>
            {proArtisan.suspensionReason && (
              <p className="text-sm text-foreground">
                <span className="font-semibold">Motif :</span> {proArtisan.suspensionReason}
              </p>
            )}
          </Card>
        )}

        {proArtisan && !isVerified ? (
          <Card padding="lg" className="space-y-4">
            <VerificationStatusBanner status={proArtisan.verifiedStatus} />
            <Button
              variant="primary"
              size="lg"
              fullWidth
              leadingIcon={<ClipboardCheck aria-hidden className="w-5 h-5" />}
              onClick={() => navigate('/pro/onboarding')}
            >
              Compléter mon profil
            </Button>
          </Card>
        ) : (
          <>
            <section aria-label="Mes indicateurs">
              {isStatsLoading && !stats ? (
                <div className="grid grid-cols-2 gap-3" aria-busy="true">
                  {[0, 1, 2, 3].map((key) => (
                    <Skeleton key={key} className="h-28 rounded-card" />
                  ))}
                </div>
              ) : statsError && !stats ? (
                <ErrorState message={statsError.message} onRetry={reloadStats} />
              ) : stats ? (
                <div className="grid grid-cols-2 gap-3">
                  <StatTile
                    icon={<Wallet className="w-5 h-5" />}
                    label="Chiffre d'affaires"
                    value={
                      stats.revenueFcfa != null ? formatFcfa(stats.revenueFcfa) : 'Non disponible'
                    }
                    hint="Montants payés, avant commission"
                  />
                  <StatTile
                    icon={<Briefcase className="w-5 h-5" />}
                    label="Interventions terminées"
                    value={String(stats.interventionsCount)}
                  />
                  <StatTile
                    icon={<Star className="w-5 h-5" />}
                    label="Note moyenne"
                    value={
                      stats.ratingAvg != null ? formatRating(stats.ratingAvg) : 'Pas encore noté'
                    }
                    hint={stats.reviewCount > 0 ? `${stats.reviewCount} avis` : undefined}
                  />
                  <StatTile
                    icon={<Clock className="w-5 h-5" />}
                    label="Taux de réponse"
                    // Valeur courte (la tuile est étroite à 360 px), explication en
                    // précision : jamais un mot coupé en deux.
                    value={
                      stats.responseRate != null ? `${Math.round(stats.responseRate * 100)} %` : '—'
                    }
                    hint={stats.responseRate != null ? undefined : 'Non communiqué'}
                  />
                </div>
              ) : null}
              <ButtonLink
                to="/pro/gains"
                variant="outline"
                fullWidth
                className="mt-3"
                leadingIcon={<Wallet aria-hidden className="w-5 h-5" />}
              >
                Mes gains
              </ButtonLink>
            </section>

            <section aria-labelledby="demandes-recues" className="space-y-4">
              <SectionHeader id="demandes-recues" title="Demandes reçues" />
              <InterventionsList groupByStatus emptyTitle="Aucune demande pour le moment." />
            </section>

            <MyReviewsSection />
          </>
        )}
      </div>
    </main>
  );
};
