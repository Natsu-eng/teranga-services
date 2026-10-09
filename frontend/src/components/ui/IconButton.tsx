import React from 'react';
import { cn } from '../../lib/cn';

export interface IconButtonProps extends Omit<React.ComponentPropsWithRef<'button'>, 'aria-label'> {
  /** Nom accessible OBLIGATOIRE : un bouton icône sans libellé est muet pour un lecteur d'écran. */
  label: string;
  /** `on-dark` : posé sur un bandeau vert profond (espace Pro, carte résultat IA). */
  tone?: 'light' | 'on-dark';
  size?: 'sm' | 'md';
}

/**
 * Bouton rond ne contenant qu'une icône (retour, partage, fermeture...).
 * Cible tactile de 44 px en taille `md`, conforme aux recommandations mobiles.
 */
export const IconButton: React.FC<IconButtonProps> = ({
  label,
  tone = 'light',
  size = 'md',
  className,
  children,
  type = 'button',
  ...props
}) => (
  <button
    {...props}
    type={type}
    aria-label={label}
    title={label}
    className={cn(
      'inline-flex shrink-0 items-center justify-center rounded-full cursor-pointer transition-colors duration-150 disabled:opacity-55 disabled:cursor-not-allowed',
      size === 'md' ? 'w-11 h-11' : 'w-9 h-9',
      tone === 'light' ? 'text-foreground hover:bg-surface-muted' : 'text-white hover:bg-white/15',
      className,
    )}
  >
    {children}
  </button>
);
