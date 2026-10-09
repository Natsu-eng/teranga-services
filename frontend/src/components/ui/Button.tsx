import React from 'react';
import { Link, type LinkProps } from 'react-router';
import { Spinner } from './Spinner';
import { buttonClasses, type ButtonSize, type ButtonVariant } from './styles';

interface ButtonOwnProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  /** Icône avant le libellé (décorative : le libellé porte le sens). */
  leadingIcon?: React.ReactNode;
  /** Icône après le libellé (décorative). */
  trailingIcon?: React.ReactNode;
}

export interface ButtonProps extends ButtonOwnProps, React.ComponentPropsWithRef<'button'> {
  /**
   * Action en cours : le bouton est désactivé, signale `aria-busy` et
   * remplace l'icône de tête par un indicateur. Le libellé reste celui
   * fourni par l'écran (ex. « Envoi en cours... »), jamais deviné ici.
   */
  isLoading?: boolean;
}

/**
 * Bouton unique de l'application. `type="button"` par défaut : un bouton
 * placé dans un formulaire ne le soumet jamais par accident ; la
 * soumission se déclare explicitement avec `type="submit"`.
 */
export const Button: React.FC<ButtonProps> = ({
  variant,
  size,
  fullWidth,
  leadingIcon,
  trailingIcon,
  isLoading = false,
  disabled,
  className,
  children,
  type = 'button',
  ...props
}) => (
  <button
    {...props}
    type={type}
    disabled={disabled || isLoading}
    aria-busy={isLoading || undefined}
    className={buttonClasses({ variant, size, fullWidth, className })}
  >
    {isLoading ? <Spinner label={null} size="sm" /> : leadingIcon}
    {children}
    {!isLoading && trailingIcon}
  </button>
);

export interface ButtonLinkProps extends ButtonOwnProps, LinkProps {}

/**
 * Lien de navigation habillé en bouton (même rendu que `Button`). À
 * préférer dès que l'action change de page : vrai <a>, ouvrable dans un
 * nouvel onglet et annoncé comme lien par les lecteurs d'écran.
 */
export const ButtonLink: React.FC<ButtonLinkProps> = ({
  variant,
  size,
  fullWidth,
  leadingIcon,
  trailingIcon,
  className,
  children,
  ...props
}) => (
  <Link {...props} className={buttonClasses({ variant, size, fullWidth, className })}>
    {leadingIcon}
    {children}
    {trailingIcon}
  </Link>
);
