import type { ReactNode } from 'react';
import { useAuth } from '../../features/auth/hooks/useAuth';
import { NotFoundScreen } from '../../features/not-found/NotFoundScreen';

interface RequireAdminRouteProps {
  children: ReactNode;
}

/**
 * Garde l'espace admin (BUILD_PLAN.md, espace admin) : un compte non-admin
 * (y compris non authentifié) voit EXACTEMENT le même écran qu'une route
 * inexistante -- jamais un message "accès refusé", jamais une redirection
 * vers /connexion, l'un comme l'autre confirmeraient que /admin/* existe.
 * Attend la fin de la restauration de session (`isLoading`) avant de
 * trancher, comme `ProtectedRoute`, pour ne pas flasher un 404 à un admin
 * dont la session est encore en cours de restauration au chargement.
 */
export function RequireAdminRoute({ children }: RequireAdminRouteProps) {
  const { role, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (role !== 'admin') {
    return <NotFoundScreen />;
  }

  return <>{children}</>;
}
