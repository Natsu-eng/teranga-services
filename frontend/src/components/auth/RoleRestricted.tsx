import React from 'react';
import { Lock } from 'lucide-react';
import type { Role, SignupRole } from '../../lib/api/auth-client';
import { ButtonLink } from '../ui/Button';

const SPACE_LABEL: Record<SignupRole, string> = {
  artisan: 'Cet espace est réservé aux artisans.',
  client: 'Cet espace est réservé aux clients.',
};

/** Page d'accueil naturelle de chaque rôle (là où le renvoyer). */
const HOME_FOR_ROLE: Record<Role, { to: string; label: string }> = {
  artisan: { to: '/pro', label: 'Aller à mon tableau de bord' },
  client: { to: '/accueil', label: "Retour à l'accueil" },
  // Un admin n'atterrit ici que par URL directe : on le renvoie vers
  // l'accueil public, jamais vers un lien qui exposerait l'espace admin.
  admin: { to: '/accueil', label: "Retour à l'accueil" },
};

interface RoleRestrictedProps {
  /** Rôle auquel l'espace est réservé (le premier des rôles autorisés). */
  reservedFor: SignupRole;
  /** Rôle réel du compte connecté, pour proposer la bonne sortie. */
  currentRole: Role | null;
}

/**
 * Refus propre d'un espace qui ne concerne pas le compte connecté (ex. un
 * client sur /pro). Ce n'est pas une mesure de sécurité — le backend
 * verrouille déjà les données par rôle — mais l'alignement du front : on
 * n'affiche jamais un écran inutilisable, on explique et on propose une
 * sortie. (L'espace admin, lui, reste indétectable : voir RequireAdminRoute.)
 */
export const RoleRestricted: React.FC<RoleRestrictedProps> = ({ reservedFor, currentRole }) => {
  const exit = HOME_FOR_ROLE[currentRole ?? 'client'];
  return (
    <main className="max-w-md mx-auto px-4 pt-12 pb-8 text-center flex flex-col items-center gap-5">
      <span
        aria-hidden
        className="inline-flex w-20 h-20 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald"
      >
        <Lock className="w-9 h-9" />
      </span>
      <div className="space-y-2">
        <h1 className="font-display text-display-md font-semibold text-primary">
          {SPACE_LABEL[reservedFor]}
        </h1>
        <p className="text-sm text-muted-foreground">
          Votre compte n&apos;a pas accès à cette page.
        </p>
      </div>
      <ButtonLink to={exit.to} variant="outline">
        {exit.label}
      </ButtonLink>
    </main>
  );
};
