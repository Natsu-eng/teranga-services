import React from 'react';
import { Link } from 'react-router';
import { useAuth } from '../../features/auth/hooks/useAuth';
import { Avatar } from '../ui/Avatar';
import { Logo } from '../ui/Logo';

/**
 * En-tête de l'espace Pro (artisan) : BANDEAU vert profond. C'est la
 * signature visuelle qui distingue l'espace artisan de l'espace client au
 * premier regard, avec exactement les mêmes composants par ailleurs.
 * `data-tone="dark"` fait passer le contour de focus à l'or.
 */
export const ProHeader: React.FC = () => {
  const auth = useAuth();

  return (
    <header data-tone="dark" className="sticky top-0 z-40 bg-primary text-white">
      <div className="max-w-5xl mx-auto flex items-center justify-between gap-3 h-16 px-4 md:px-8">
        <Link to="/pro" aria-label="Téranga Pro, tableau de bord" className="rounded-xl">
          <Logo variant="pro" tone="on-dark" />
        </Link>
        {auth.user && (
          <Link to="/profil" aria-label="Mon profil" className="shrink-0 rounded-full">
            <Avatar
              name={auth.user.fullName}
              size="sm"
              decorative
              className="ring-2 ring-white/30"
            />
          </Link>
        )}
      </div>
    </header>
  );
};
