import React from 'react';

/**
 * Lien d'évitement : premier élément atteint à la tabulation, il permet
 * aux utilisateurs clavier de sauter l'en-tête et d'aller directement au
 * contenu (`#contenu`). Invisible tant qu'il n'a pas le focus.
 */
export const SkipLink: React.FC = () => (
  <a
    href="#contenu"
    className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-full focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
  >
    Aller au contenu
  </a>
);
