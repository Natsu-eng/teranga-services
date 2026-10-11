import React from 'react';
import { Link, type LinkProps } from 'react-router';
import { chipClasses } from './styles';

export interface ChipProps extends React.ComponentPropsWithRef<'button'> {
  selected?: boolean;
  icon?: React.ReactNode;
}

/**
 * Pastille de filtre (métier, note minimale...). Bouton bascule : son état
 * est exposé par `aria-pressed`, pas seulement par la couleur.
 */
export const Chip: React.FC<ChipProps> = ({
  selected = false,
  icon,
  className,
  children,
  type = 'button',
  ...props
}) => (
  <button
    {...props}
    type={type}
    aria-pressed={selected}
    className={chipClasses(selected, className)}
  >
    {icon}
    {children}
  </button>
);

export interface ChipLinkProps extends LinkProps {
  icon?: React.ReactNode;
}

/** Pastille qui navigue (ex. métier sur l'accueil -> recherche filtrée). */
export const ChipLink: React.FC<ChipLinkProps> = ({ icon, className, children, ...props }) => (
  <Link {...props} className={chipClasses(false, className)}>
    {icon}
    {children}
  </Link>
);
