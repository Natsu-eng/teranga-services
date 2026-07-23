import React from 'react';
import { Link } from 'react-router';
import { Compass } from 'lucide-react';

export const NotFoundScreen: React.FC = () => (
  <main className="min-h-screen flex flex-col items-center justify-center text-center px-4 py-24 gap-4">
    <div className="w-14 h-14 rounded-full bg-surface-muted flex items-center justify-center text-muted-foreground">
      <Compass className="w-7 h-7" />
    </div>

    <h1 className="font-headline-md text-2xl font-bold text-primary">Page introuvable</h1>
    <p className="text-sm text-muted-foreground max-w-xs">
      Cette page n&apos;existe pas ou n&apos;est plus disponible.
    </p>

    <Link
      to="/accueil"
      className="mt-2 px-5 py-2.5 rounded-full bg-primary text-white font-sora text-xs font-bold hover:opacity-90 active:scale-95 transition-all"
    >
      Retour à l&apos;accueil
    </Link>
  </main>
);
