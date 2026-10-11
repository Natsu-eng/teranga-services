import React from 'react';
import { cn } from '../../lib/cn';

export interface IconButtonProps extends Omit<React.ComponentPropsWithRef<'button'>, 'aria-label'> {
  /** Nom accessible OBLIGATOIRE : un bouton icône sans libellé est muet pour un lecteur d'écran. */
  label: string;
  /**
   * `on-dark` : posé sur un bandeau vert profond (espace Pro, carte résultat IA).
   * `danger`  : action destructive (retirer, supprimer).
   * `brand`   : action principale d'une barre (ex. « Envoyer » un message).
   */
  tone?: 'light' | 'on-dark' | 'danger' | 'brand';
  size?: 'sm' | 'md';
}

const ICON_BUTTON_TONES = {
  light: 'text-foreground hover:bg-surface-muted',
  'on-dark': 'text-white hover:bg-white/15',
  danger: 'text-destructive hover:bg-destructive-soft',
  brand: 'bg-primary-emerald text-white hover:bg-primary disabled:bg-border-strong',
} as const;

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
      ICON_BUTTON_TONES[tone],
      className,
    )}
  >
    {children}
  </button>
);
