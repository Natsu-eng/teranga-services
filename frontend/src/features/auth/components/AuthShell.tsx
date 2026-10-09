import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { IconButton } from '../../../components/ui/IconButton';
import { Logo } from '../../../components/ui/Logo';

interface AuthShellProps {
  title: string;
  description?: React.ReactNode;
  /** Bouton retour en haut à gauche (absent sur le premier écran du parcours). */
  onBack?: () => void;
  children: React.ReactNode;
}

/**
 * Gabarit commun du parcours de connexion / inscription : logo, retour,
 * titre Fraunces (h1) et description, puis le contenu de l'étape. Une
 * colonne étroite et aérée, identique d'une étape à l'autre pour que le
 * parcours se lise comme une seule suite.
 */
export const AuthShell: React.FC<AuthShellProps> = ({ title, description, onBack, children }) => (
  <main className="min-h-screen max-w-md mx-auto px-4 pt-4 pb-10 flex flex-col">
    <div className="flex items-center justify-between h-12">
      {onBack ? (
        <IconButton label="Retour" onClick={onBack} className="-ml-2">
          <ArrowLeft aria-hidden className="w-6 h-6" />
        </IconButton>
      ) : (
        <span />
      )}
      <Logo />
      {/* Équilibre visuel du logo centré. */}
      <span className="w-11" aria-hidden />
    </div>

    <div className="pt-10 pb-8 space-y-2">
      <h1 className="font-display text-display-lg font-semibold text-primary">{title}</h1>
      {description && <p className="text-base text-muted-foreground">{description}</p>}
    </div>

    <div className="flex-1 flex flex-col">{children}</div>
  </main>
);
