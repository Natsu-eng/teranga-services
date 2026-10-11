import React from 'react';
import {
  ChevronRight,
  ClipboardList,
  CreditCard,
  ExternalLink,
  LayoutDashboard,
  LogOut,
  MapPin,
  Receipt,
  Sparkles,
  UserRoundCog,
  Wallet,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ErrorState } from '../../components/ui/ErrorState';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { VerifiedBadge } from '../../components/ui/VerifiedBadge';
import { cn } from '../../lib/cn';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { VerificationStatusBanner } from '../artisans/VerificationStatusBanner';
import { useMyArtisanProfile } from '../artisans/hooks/useMyArtisanProfile';
import { IdentityCard } from './components/IdentityCard';
import { useCurrentUser } from './hooks/useCurrentUser';

interface MenuLinkProps {
  to: string;
  icon: LucideIcon;
  label: string;
  description: string;
}

/** Entrée de menu : une ligne cliquable, icône + libellé + explication. */
const MenuLink: React.FC<MenuLinkProps> = ({ to, icon: Icon, label, description }) => (
  <li>
    <Link
      to={to}
      className="flex items-center gap-3 rounded-field px-3 py-3 hover:bg-surface-muted transition-colors"
    >
      <span
        aria-hidden
        className="inline-flex w-10 h-10 shrink-0 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald"
      >
        <Icon className="w-5 h-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-foreground">{label}</span>
        <span className="block text-sm text-muted-foreground">{description}</span>
      </span>
      <ChevronRight aria-hidden className="w-5 h-5 text-muted-foreground shrink-0" />
    </Link>
  </li>
);

const LogoutCard: React.FC = () => {
  const auth = useAuth();
  const navigate = useNavigate();
  return (
    <Card padding="sm">
      <Button
        variant="danger-ghost"
        fullWidth
        leadingIcon={<LogOut aria-hidden className="w-5 h-5" />}
        onClick={async () => {
          await auth.logout();
          navigate('/');
        }}
      >
        Déconnexion
      </Button>
    </Card>
  );
};

/* ------------------------------------------------------------------ Client */

/** Moyens de paiement locaux, présentés pour information (aucun paiement en ligne encore). */
const PAYMENT_METHODS = [
  { label: 'Wave', mark: 'W', className: 'bg-brand-wave text-foreground' },
  { label: 'Orange Money', mark: 'OM', className: 'bg-brand-orange-money text-foreground' },
] as const;

/**
 * Profil d'un CLIENT : tout est orienté vers ses besoins de services
 * (demandes, interventions, nouvelle demande).
 */
const ClientProfile: React.FC<{ name: string; location: string; phone?: string | null }> = ({
  name,
  location,
  phone,
}) => (
  <>
    <IdentityCard
      name={name}
      phone={phone}
      subtitle={
        <span className="inline-flex items-center gap-1">
          <MapPin aria-hidden className="w-4 h-4" />
          {location}
        </span>
      }
      badge={<StatusPill tone="info">Compte client</StatusPill>}
    />

    <section aria-labelledby="mes-services" className="space-y-3">
      <SectionHeader id="mes-services" title="Mes services" />
      <Card padding="sm">
        <ul>
          <MenuLink
            to="/demande"
            icon={Sparkles}
            label="Nouvelle demande"
            description="Décrivez un besoin, l'assistant trouve le bon métier."
          />
          <MenuLink
            to="/mes-demandes"
            icon={ClipboardList}
            label="Mes demandes"
            description="Vos besoins décrits et leur avancement."
          />
          <MenuLink
            to="/mes-interventions"
            icon={Wrench}
            label="Devis et travaux"
            description="Devis des artisans à accepter, travaux en cours, avis à laisser."
          />
          <MenuLink
            to="/mes-paiements"
            icon={Receipt}
            label="Mes paiements"
            description="Ce que vous avez payé, en séquestre ou remboursé."
          />
        </ul>
      </Card>
    </section>

    {/*
      Section informative : le moyen se choisit au moment de payer un devis
      (écran de paiement), jamais enregistré à l'avance.
    */}
    <section aria-labelledby="paiement" className="space-y-3">
      <SectionHeader id="paiement" title="Moyens de paiement au Sénégal" />
      <Card className="space-y-3">
        <ul className="flex flex-wrap gap-2">
          {PAYMENT_METHODS.map((method) => (
            <li
              key={method.label}
              className="inline-flex items-center gap-2 rounded-full bg-surface-muted pl-1 pr-3 py-1 text-sm text-foreground"
            >
              <span
                aria-hidden
                className={cn(
                  'inline-flex w-7 h-7 items-center justify-center rounded-full text-xs font-bold',
                  method.className,
                )}
              >
                {method.mark}
              </span>
              {method.label}
            </li>
          ))}
          <li className="inline-flex items-center gap-2 rounded-full bg-surface-muted pl-1 pr-3 py-1 text-sm text-foreground">
            <span
              aria-hidden
              className="inline-flex w-7 h-7 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald"
            >
              <CreditCard className="w-4 h-4" />
            </span>
            Carte bancaire
          </li>
        </ul>
        <p className="text-sm text-muted-foreground">
          Payez un devis accepté depuis le suivi de vos travaux, ou réglez l&apos;artisan en
          espèces. En ligne, Téranga conserve votre argent et ne le verse à l&apos;artisan
          qu&apos;après votre confirmation de fin des travaux.
        </p>
      </Card>
    </section>

    <LogoutCard />
  </>
);

/* ----------------------------------------------------------------- Artisan */

/**
 * Profil d'un ARTISAN : orienté vers son activité. Statut de vérification,
 * accès au tableau de bord, à l'édition complète du profil Pro (photo,
 * présentation, métiers, tarifs, documents) et à sa fiche publique.
 * Aucun moyen de paiement client ici : l'artisan règle où il est payé
 * (moyen de versement), dans ses gains.
 */
const ArtisanProfile: React.FC<{
  name: string;
  artisanId: string | null;
  phone?: string | null;
}> = ({ name, artisanId, phone }) => {
  const { data: profile, isLoading, error, reload } = useMyArtisanProfile(artisanId);
  const isVerified = profile?.verifiedStatus === 'verified';

  return (
    <>
      <IdentityCard
        name={name}
        phone={phone}
        avatarUrl={profile?.avatarUrl}
        subtitle={<span>Artisan · Téranga Pro</span>}
        badge={isVerified ? <VerifiedBadge /> : undefined}
      />

      {isLoading && !profile ? (
        <Skeleton className="h-20 rounded-card" />
      ) : error && !profile ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : profile ? (
        <VerificationStatusBanner status={profile.verifiedStatus} />
      ) : null}

      <section aria-labelledby="mon-activite" className="space-y-3">
        <SectionHeader id="mon-activite" title="Mon activité" />
        <Card padding="sm">
          <ul>
            <MenuLink
              to="/pro"
              icon={LayoutDashboard}
              label="Tableau de bord"
              description="Disponibilité, demandes reçues, revenus."
            />
            <MenuLink
              to="/pro/gains"
              icon={Wallet}
              label="Mes gains et versements"
              description="Ce que vous touchez, commissions prélevées, moyen de versement."
            />
            <MenuLink
              to="/pro/onboarding"
              icon={UserRoundCog}
              label="Modifier mon profil Pro"
              description="Photo, présentation, métiers et tarifs, documents."
            />
            {artisanId && (
              <MenuLink
                to={`/artisans/${artisanId}`}
                icon={ExternalLink}
                label="Voir ma fiche publique"
                description="Telle que les clients la voient."
              />
            )}
          </ul>
        </Card>
      </section>

      <LogoutCard />
    </>
  );
};

/* ----------------------------------------------------------------- Écran */

interface UserProfileScreenProps {
  location: string;
}

/**
 * Profil (/profil) : deux écrans distincts selon le rôle du compte
 * (toujours dérivé du serveur, auth.role), chacun orienté vers son usage.
 */
export const UserProfileScreen: React.FC<UserProfileScreenProps> = ({ location }) => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);
  const { data: currentUser, isLoading, error, reload } = useCurrentUser();

  return (
    <main className="max-w-3xl mx-auto px-4 md:px-8 pt-2 space-y-6">
      {isLoading && !currentUser ? (
        <Card padding="lg" className="flex items-center gap-4" aria-busy="true">
          <Skeleton className="w-18 h-18 rounded-full shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-24" />
          </div>
        </Card>
      ) : error && !currentUser ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : currentUser ? (
        role === 'artisan' ? (
          <ArtisanProfile
            name={currentUser.name}
            artisanId={currentUser.artisanId}
            phone={auth.user?.phone}
          />
        ) : (
          <ClientProfile name={currentUser.name} location={location} phone={auth.user?.phone} />
        )
      ) : null}
    </main>
  );
};
