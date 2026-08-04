import React from 'react';
import { ShieldAlert, ShieldCheck, ShieldX } from 'lucide-react';
import type { ArtisanVerifiedStatus } from '../../types';

interface CopyEntry {
  title: string;
  description: string;
}

const COPY: Record<ArtisanVerifiedStatus, CopyEntry> = {
  none: {
    title: 'Complétez votre profil pour démarrer la vérification',
    description:
      "Renseignez votre profil, déclarez vos métiers et envoyez vos documents d'identité.",
  },
  pending: {
    title: 'Votre compte est en cours de vérification',
    description: 'Vous ne recevrez pas encore de demandes tant que vos documents ne sont pas validés.',
  },
  rejected: {
    title: 'Un ou plusieurs documents ont été refusés',
    description: 'Consultez le motif ci-dessous puis renvoyez un document valide.',
  },
  verified: {
    title: 'Votre compte est vérifié',
    description: 'Vous êtes visible dans les recherches et pouvez recevoir des demandes.',
  },
};

/**
 * Bandeau de statut explicite, toujours visible (BUILD_PLAN.md, onboarding
 * artisan §6/§7) : un artisan non vérifié ne doit jamais être laissé à
 * deviner pourquoi il ne reçoit pas de demandes. Affiché à la fois sur
 * l'écran d'onboarding et sur `/pro` (ArtisanDashboardScreen) pour que le
 * message reste cohérent où que l'artisan atterrisse.
 */
export const VerificationStatusBanner: React.FC<{ status: ArtisanVerifiedStatus }> = ({
  status,
}) => {
  const copy = COPY[status];
  const isRejected = status === 'rejected';
  const isVerified = status === 'verified';
  const Icon = isRejected ? ShieldX : isVerified ? ShieldCheck : ShieldAlert;

  const toneClasses = isRejected
    ? 'bg-destructive-soft border-destructive/30'
    : isVerified
      ? 'bg-success/40 border-success'
      : 'bg-accent-soft border-accent/30';
  const iconClasses = isRejected
    ? 'text-destructive'
    : isVerified
      ? 'text-success-foreground'
      : 'text-accent-foreground-strong';

  return (
    <div className={`rounded-2xl p-4 flex items-start gap-3 border ${toneClasses}`} role="status">
      <Icon className={`w-5 h-5 shrink-0 mt-0.5 ${iconClasses}`} />
      <div>
        <p className="font-sora text-sm font-bold text-foreground">{copy.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{copy.description}</p>
      </div>
    </div>
  );
};
