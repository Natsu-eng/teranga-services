import React from 'react';
import { cn } from '../../lib/cn';

interface StatTileProps {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  /** Précision sous la valeur (ex. « 12 avis »). */
  hint?: string;
  /** `default` : carte blanche · `on-dark` : posée sur un bandeau vert profond. */
  tone?: 'default' | 'on-dark';
  className?: string;
}

/**
 * Indicateur chiffré (revenus, note, expérience...). La valeur est en
 * Fraunces, le libellé en petites capitales : lisible d'un coup d'œil.
 * L'ordre DOM (libellé puis valeur) donne une lecture naturelle aux
 * lecteurs d'écran (« Revenus : 45 000 FCFA ») ; l'ordre visuel met la
 * valeur en avant.
 */
export const StatTile: React.FC<StatTileProps> = ({
  label,
  value,
  icon,
  hint,
  tone = 'default',
  className,
}) => (
  <div
    className={cn(
      'rounded-card p-4 flex flex-col gap-1 min-w-0',
      tone === 'default' ? 'bg-surface shadow-card' : 'bg-white/10 text-white',
      className,
    )}
  >
    {icon && (
      <span
        aria-hidden
        className={cn(
          'mb-1 inline-flex w-9 h-9 items-center justify-center rounded-full',
          tone === 'default' ? 'bg-emerald-tint text-primary-emerald' : 'bg-white/15 text-accent',
        )}
      >
        {icon}
      </span>
    )}
    <span
      className={cn(
        'order-3 text-caption font-semibold uppercase tracking-wider',
        tone === 'default' ? 'text-muted-foreground' : 'text-primary-emerald-foreground',
      )}
    >
      {label}
    </span>
    <span
      className={cn(
        'order-2 font-display text-display-sm font-semibold break-words',
        tone === 'default' ? 'text-primary' : 'text-white',
      )}
    >
      {value}
    </span>
    {hint && (
      <span
        className={cn(
          'order-4 text-xs',
          tone === 'default' ? 'text-muted-foreground' : 'text-primary-emerald-foreground',
        )}
      >
        {hint}
      </span>
    )}
  </div>
);
