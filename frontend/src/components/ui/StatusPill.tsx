import React from 'react';
import { cn } from '../../lib/cn';

/**
 * Tonalités d'état, toutes au-dessus de 4,5:1 de contraste :
 * - neutral : sans enjeu (expirée, brouillon)
 * - info    : en cours, la plateforme ou l'autre partie agit
 * - success : abouti (terminée, validé)
 * - warning : attend une action ou une réponse
 * - danger  : refusé, annulé, litige
 */
export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

const TONES: Record<StatusTone, { pill: string; dot: string }> = {
  neutral: { pill: 'bg-surface-muted text-muted-foreground', dot: 'bg-muted-foreground-soft' },
  info: { pill: 'bg-emerald-tint text-primary', dot: 'bg-primary-emerald' },
  success: { pill: 'bg-success text-success-foreground', dot: 'bg-primary-emerald' },
  warning: { pill: 'bg-accent-soft text-accent-foreground-strong', dot: 'bg-accent' },
  danger: { pill: 'bg-destructive-soft text-destructive', dot: 'bg-destructive' },
};

interface StatusPillProps {
  tone: StatusTone;
  children: React.ReactNode;
  className?: string;
}

/** Pastille d'état (demande, intervention, document). Le texte porte le sens, la couleur le renforce. */
export const StatusPill: React.FC<StatusPillProps> = ({ tone, children, className }) => (
  <span
    className={cn(
      'inline-flex shrink-0 items-center gap-1.5 rounded-full h-6 px-2.5 text-xs font-semibold whitespace-nowrap',
      TONES[tone].pill,
      className,
    )}
  >
    <span aria-hidden className={cn('w-1.5 h-1.5 rounded-full', TONES[tone].dot)} />
    {children}
  </span>
);
