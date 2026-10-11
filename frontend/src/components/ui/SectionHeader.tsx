import React from 'react';
import { cn } from '../../lib/cn';

interface SectionHeaderProps {
  title: string;
  /** Niveau de titre réel (hiérarchie du document), indépendant de la taille visuelle. */
  as?: 'h1' | 'h2' | 'h3';
  /** `lg` : titre de page · `md` : titre de section. */
  size?: 'md' | 'lg';
  /** Petit sur-titre au-dessus (ex. « Espace Pro »). */
  eyebrow?: string;
  description?: React.ReactNode;
  /** Action alignée à droite (ex. lien « Voir tout »). */
  action?: React.ReactNode;
  /** Pour relier une section à son titre (`aria-labelledby`). */
  id?: string;
  /** `on-dark` : sur un bandeau vert profond. */
  tone?: 'default' | 'on-dark';
  className?: string;
}

/** Titre de page ou de section, en Fraunces, avec action optionnelle. */
export const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  as: Heading = 'h2',
  size = 'md',
  eyebrow,
  description,
  action,
  id,
  tone = 'default',
  className,
}) => (
  <div className={cn('flex items-end justify-between gap-4', className)}>
    <div className="min-w-0 space-y-1">
      {eyebrow && (
        <p
          className={cn(
            'text-caption font-semibold uppercase tracking-[0.12em]',
            tone === 'default' ? 'text-accent-foreground' : 'text-accent',
          )}
        >
          {eyebrow}
        </p>
      )}
      <Heading
        id={id}
        className={cn(
          'font-display font-semibold',
          size === 'lg' ? 'text-display-md' : 'text-display-sm',
          tone === 'default' ? 'text-primary' : 'text-white',
        )}
      >
        {title}
      </Heading>
      {description && (
        <p
          className={cn(
            'text-sm',
            tone === 'default' ? 'text-muted-foreground' : 'text-primary-emerald-foreground',
          )}
        >
          {description}
        </p>
      )}
    </div>
    {action && <div className="shrink-0">{action}</div>}
  </div>
);
