import React from 'react';
import { Clock3 } from 'lucide-react';
import { ButtonLink } from './Button';

interface ComingSoonProps {
  title?: string;
  description?: string;
  /** Lien de retour (ex. `/pro` pour un artisan). */
  backTo?: string;
}

/**
 * Écran honnête pour une fonctionnalité que le backend ne sert pas encore
 * (messagerie) : ni erreur, ni page blanche, ni données fictives — un « pas
 * encore » assumé, dans le style de l'app.
 */
export const ComingSoon: React.FC<ComingSoonProps> = ({
  title = 'Bientôt disponible',
  description = 'Cette fonctionnalité arrive prochainement. Merci de votre patience.',
  backTo = '/accueil',
}) => (
  <main className="max-w-md mx-auto px-4 pt-16 pb-28 text-center flex flex-col items-center gap-5">
    <span
      aria-hidden
      className="inline-flex w-20 h-20 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald"
    >
      <Clock3 className="w-9 h-9" />
    </span>
    <div className="space-y-2">
      <h1 className="font-display text-display-md font-semibold text-primary">{title}</h1>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
    <ButtonLink to={backTo} variant="outline">
      Retour à l&apos;accueil
    </ButtonLink>
  </main>
);
