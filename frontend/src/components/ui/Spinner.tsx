import React from 'react';
import { cn } from '../../lib/cn';

interface SpinnerProps {
  /** Libellé lu par les lecteurs d'écran. `null` = décoratif (ex. dans un bouton déjà libellé). */
  label?: string | null;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const SIZES = {
  sm: 'w-4 h-4 border-2',
  md: 'w-6 h-6 border-2',
  lg: 'w-9 h-9 border-[3px]',
} as const;

/**
 * Indicateur d'activité. La couleur suit `currentColor` : il s'adapte seul
 * au bouton ou au bandeau qui le contient. En reduced-motion, la rotation
 * est neutralisée par la règle globale (index.css) : l'anneau reste visible.
 */
export const Spinner: React.FC<SpinnerProps> = ({
  label = 'Chargement',
  size = 'md',
  className,
}) => (
  <span
    {...(label ? { role: 'status', 'aria-label': label } : { 'aria-hidden': true })}
    className={cn(
      'inline-block shrink-0 rounded-full border-current border-t-transparent animate-spin',
      SIZES[size],
      className,
    )}
  />
);

/** Chargement plein écran (restauration de session, garde de route). */
export const PageLoader: React.FC<{ label?: string }> = ({ label = 'Chargement' }) => (
  <div className="min-h-screen flex items-center justify-center bg-background text-primary-emerald">
    <Spinner label={label} size="lg" />
  </div>
);
