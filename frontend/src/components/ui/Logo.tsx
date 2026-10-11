import React from 'react';
import { cn } from '../../lib/cn';

interface LogoProps {
  /** `pro` ajoute la mention « Pro » en or (espace artisan). */
  variant?: 'default' | 'pro';
  /** `on-dark` : sur fond vert profond. */
  tone?: 'light' | 'on-dark';
  className?: string;
}

/**
 * Signature de marque : monogramme « T » + nom en Fraunces. Purement
 * typographique (aucune image à charger). Le texte reste lisible par les
 * lecteurs d'écran (« Téranga », « Téranga Pro »).
 */
export const Logo: React.FC<LogoProps> = ({ variant = 'default', tone = 'light', className }) => {
  const onDark = tone === 'on-dark';
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span
        aria-hidden
        className={cn(
          'inline-flex w-8 h-8 items-center justify-center rounded-xl font-display text-lg font-bold leading-none',
          onDark ? 'bg-accent text-primary' : 'bg-primary text-accent',
        )}
      >
        T
      </span>
      <span
        className={cn(
          'font-display text-xl font-semibold tracking-tight',
          onDark ? 'text-white' : 'text-primary',
        )}
      >
        Téranga
        {variant === 'pro' && (
          <span
            className={cn(
              'ml-1.5 align-middle inline-flex items-center rounded-md px-1.5 py-0.5 font-sans text-caption font-bold uppercase tracking-wider',
              onDark ? 'bg-accent text-primary' : 'bg-primary text-accent',
            )}
          >
            Pro
          </span>
        )}
      </span>
    </span>
  );
};
