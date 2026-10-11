import React from 'react';
import { ShieldAlert, ShieldX } from 'lucide-react';
import { VerifiedBadge } from '../../components/ui/VerifiedBadge';
import { cn } from '../../lib/cn';
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
    description:
      'Vous ne recevrez pas encore de demandes tant que vos documents ne sont pas validés.',
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

const TONES: Record<ArtisanVerifiedStatus, string> = {
  none: 'bg-accent-soft text-accent-foreground-strong',
  pending: 'bg-accent-soft text-accent-foreground-strong',
  rejected: 'bg-destructive-soft text-destructive',
  verified: 'bg-emerald-tint text-primary',
};

/**
 * Bandeau de statut explicite, toujours visible (BUILD_PLAN.md, onboarding
 * artisan §6/§7) : un artisan non vérifié ne doit jamais être laissé à
 * deviner pourquoi il ne reçoit pas de demandes. Affiché sur l'onboarding,
 * le tableau de bord et le profil, avec le même message partout. Une fois
 * vérifié, l'artisan voit le même badge que ses clients.
 */
export const VerificationStatusBanner: React.FC<{ status: ArtisanVerifiedStatus }> = ({
  status,
}) => {
  const copy = COPY[status];
  const Icon = status === 'rejected' ? ShieldX : ShieldAlert;

  return (
    <div role="status" className={cn('rounded-card p-4 flex items-start gap-3', TONES[status])}>
      {status === 'verified' ? (
        <VerifiedBadge size="md" className="mt-0.5" />
      ) : (
        <Icon aria-hidden className="w-5 h-5 shrink-0 mt-0.5" />
      )}
      <div className="min-w-0">
        <p className="text-sm font-semibold">{copy.title}</p>
        <p className="text-sm text-foreground/80 mt-0.5">{copy.description}</p>
      </div>
    </div>
  );
};
