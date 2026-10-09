import React from 'react';
import { cardClasses, type CardPadding, type CardTone } from './styles';

type CardElement = 'div' | 'section' | 'article' | 'li' | 'aside';

export interface CardProps extends React.HTMLAttributes<HTMLElement> {
  /** Élément HTML rendu : `section`/`article` quand la carte porte un titre, `li` dans une liste. */
  as?: CardElement;
  tone?: CardTone;
  padding?: CardPadding;
  interactive?: boolean;
}

/**
 * Carte de base : coins ~20 px, ombre diffuse, jamais de bordure dure.
 * Pour une carte cliquable qui navigue, habiller directement un <Link> avec
 * `cardClasses({ interactive: true })` (styles.ts) plutôt que d'imbriquer
 * un lien dans une carte.
 */
export const Card: React.FC<CardProps> = ({
  as: Tag = 'div',
  tone = 'default',
  padding = 'md',
  interactive = false,
  className,
  children,
  ...props
}) => (
  <Tag
    {...props}
    // Sur fond vert profond, le contour de focus passe à l'or (index.css).
    data-tone={tone === 'dark' ? 'dark' : undefined}
    className={cardClasses({ tone, padding, interactive, className })}
  >
    {children}
  </Tag>
);
