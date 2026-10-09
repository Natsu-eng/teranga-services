import React from 'react';
import { ShieldCheck } from 'lucide-react';
import { cn } from '../../lib/cn';

interface VerifiedBadgeProps {
  /** `sm` : cartes de liste · `md` : en-têtes · `lg` : fiche artisan. */
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const SIZES = {
  sm: { pill: 'h-6 px-2 gap-1 text-caption', icon: 'w-3.5 h-3.5' },
  md: { pill: 'h-7 px-2.5 gap-1.5 text-xs', icon: 'w-4 h-4' },
  lg: { pill: 'h-9 px-3.5 gap-2 text-sm', icon: 'w-5 h-5' },
} as const;

/**
 * Signal de confiance central de Téranga : un artisan dont l'identité et
 * les documents ont été validés par l'équipe (verified_status = verified).
 *
 * Volontairement FORT et identique partout : pastille émeraude pleine,
 * texte blanc (contraste 8,2:1), icône bouclier-check. À n'afficher que
 * pour un statut réellement vérifié côté serveur — jamais en décoration.
 */
export const VerifiedBadge: React.FC<VerifiedBadgeProps> = ({ size = 'sm', className }) => {
  const s = SIZES[size];
  return (
    <span
      title="Identité et documents vérifiés par Téranga Services"
      className={cn(
        'inline-flex shrink-0 items-center rounded-full bg-primary-emerald text-white font-semibold leading-none shadow-sm',
        s.pill,
        className,
      )}
    >
      <ShieldCheck aria-hidden className={s.icon} strokeWidth={2.25} />
      Vérifié
    </span>
  );
};
