import React from 'react';
import { cn } from '../../lib/cn';
import { Button } from './Button';

interface EmptyStateProps {
  /** Icône (lucide) affichée dans une pastille vert clair. */
  icon?: React.ReactNode;
  title: string;
  description?: string;
  /** Action simple (bouton contour). Pour un lien ou plusieurs actions, passer `children`. */
  action?: { label: string; onClick: () => void };
  /** `card` : carte blanche autonome · `plain` : sans carte, dans un conteneur existant. */
  tone?: 'card' | 'plain';
  className?: string;
  children?: React.ReactNode;
}

/**
 * État vide : explique pourquoi il n'y a rien et, si possible, propose la
 * suite (réinitialiser, décrire un problème...). Jamais une zone blanche
 * muette.
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  tone = 'card',
  className,
  children,
}) => (
  <div
    className={cn(
      'flex flex-col items-center text-center gap-3 px-6',
      tone === 'card' ? 'bg-surface rounded-card shadow-card py-10' : 'py-8',
      className,
    )}
  >
    {icon && (
      <span
        aria-hidden
        className="inline-flex w-14 h-14 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald [&>svg]:w-7 [&>svg]:h-7"
      >
        {icon}
      </span>
    )}
    <div className="space-y-1 max-w-sm">
      <p className="font-display text-title font-semibold text-foreground">{title}</p>
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
    </div>
    {action && (
      <Button variant="outline" size="sm" onClick={action.onClick}>
        {action.label}
      </Button>
    )}
    {children}
  </div>
);
