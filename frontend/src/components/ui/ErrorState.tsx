import React from 'react';
import { AlertTriangle, RotateCw } from 'lucide-react';
import { cn } from '../../lib/cn';
import { Button } from './Button';

interface ErrorStateProps {
  /** Message déjà affichable (les erreurs d'API sont rédigées en français côté backend). */
  message: string;
  onRetry: () => void;
  className?: string;
}

/**
 * Échec d'un chargement : message clair et bouton « Réessayer » qui relance
 * l'appel. Annoncé immédiatement aux lecteurs d'écran (`role="alert"`).
 */
export const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry, className }) => (
  <div
    role="alert"
    className={cn(
      'flex flex-col items-center justify-center text-center gap-3 py-10 px-6 bg-surface rounded-card shadow-card',
      className,
    )}
  >
    <span
      aria-hidden
      className="inline-flex w-14 h-14 items-center justify-center rounded-full bg-destructive-soft text-destructive"
    >
      <AlertTriangle className="w-7 h-7" />
    </span>
    <p className="text-sm text-muted-foreground max-w-xs">{message}</p>
    <Button
      variant="brand"
      size="sm"
      onClick={onRetry}
      leadingIcon={<RotateCw aria-hidden className="w-4 h-4" />}
    >
      Réessayer
    </Button>
  </div>
);
