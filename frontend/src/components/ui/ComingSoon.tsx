import React from 'react';
import { Clock3 } from 'lucide-react';
import { Link } from 'react-router';

interface ComingSoonProps {
  title?: string;
  description?: string;
}

/**
 * An honest placeholder for screens the backend doesn't cover yet (chat,
 * artisan dashboard) — used instead of continuing to serve mock data once
 * a real backend exists (Lot 10). Not an error, not a blank page: a
 * deliberate, on-brand "not yet" state.
 */
export const ComingSoon: React.FC<ComingSoonProps> = ({
  title = 'Bientôt disponible',
  description = 'Cette fonctionnalité arrive prochainement. Merci de votre patience.',
}) => (
  <main className="max-w-md mx-auto px-4 pt-24 pb-28 text-center space-y-4">
    <div className="w-16 h-16 mx-auto rounded-full bg-surface-muted flex items-center justify-center">
      <Clock3 className="w-8 h-8 text-muted-foreground-soft" />
    </div>
    <h2 className="font-bold text-xl text-primary">{title}</h2>
    <p className="text-sm text-muted-foreground">{description}</p>
    <Link
      to="/accueil"
      className="inline-block mt-2 text-sm font-sora text-primary underline decoration-1 underline-offset-2"
    >
      Retour à l&apos;accueil
    </Link>
  </main>
);
