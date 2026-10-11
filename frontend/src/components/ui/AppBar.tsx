import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { cn } from '../../lib/cn';
import { useBackNavigation } from '../../lib/useBackNavigation';
import { IconButton } from './IconButton';

interface AppBarProps {
  title: string;
  /**
   * Destination du bouton retour quand il n'existe aucune page précédente
   * dans l'app (lien profond) — voir useBackNavigation.
   */
  backTo?: string;
  /** Remplace entièrement le comportement du retour (parcours guidés). */
  onBack?: () => void;
  /** Actions à droite (partage...). */
  actions?: React.ReactNode;
  /** `light` : espace client · `pro` : bandeau vert profond de l'espace Pro. */
  tone?: 'light' | 'pro';
  /** Ligne secondaire sous le titre. */
  subtitle?: string;
}

/**
 * En-tête des sous-pages (fiche artisan, demande IA, mes demandes...) :
 * bouton retour, titre de la page (h1), actions éventuelles. Collant en
 * haut d'écran. En tonalité `pro`, il prolonge le bandeau vert profond qui
 * signe l'espace artisan.
 */
export const AppBar: React.FC<AppBarProps> = ({
  title,
  backTo = '/accueil',
  onBack,
  actions,
  tone = 'light',
  subtitle,
}) => {
  const goBack = useBackNavigation(backTo);
  const isPro = tone === 'pro';

  return (
    <header
      data-tone={isPro ? 'dark' : undefined}
      className={cn(
        'sticky top-0 z-40 flex items-center gap-1 h-16 px-2 md:px-6',
        isPro
          ? 'bg-primary text-white'
          : 'bg-background/90 backdrop-blur-md text-foreground border-b border-border-faint',
      )}
    >
      <IconButton label="Retour" tone={isPro ? 'on-dark' : 'light'} onClick={onBack ?? goBack}>
        <ArrowLeft aria-hidden className="w-6 h-6" />
      </IconButton>
      <div className="min-w-0 flex-1">
        <h1
          className={cn(
            'font-display text-display-sm font-semibold truncate',
            isPro ? 'text-white' : 'text-primary',
          )}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            className={cn(
              'text-xs truncate',
              isPro ? 'text-primary-emerald-foreground' : 'text-muted-foreground',
            )}
          >
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-1 shrink-0">{actions}</div>}
    </header>
  );
};
