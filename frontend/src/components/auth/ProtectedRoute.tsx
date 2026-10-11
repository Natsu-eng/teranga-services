import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import type { SignupRole } from '../../lib/api/auth-client';
import { useAuth } from '../../features/auth/hooks/useAuth';
import { PageLoader } from '../ui/Spinner';
import { RoleRestricted } from './RoleRestricted';

interface ProtectedRouteProps {
  children: ReactNode;
  /**
   * Rôles autorisés. Absent = tout compte connecté (profil, messagerie).
   * Volontairement limité à client/artisan : l'espace admin ne passe JAMAIS
   * par cette garde (elle redirige vers /connexion et afficherait un refus
   * explicite, deux indices de son existence) mais par RequireAdminRoute.
   */
  roles?: readonly SignupRole[];
}

/**
 * Garde des espaces personnels.
 *
 * 1. Attend la fin de la restauration de session (`isLoading`) avant de
 *    trancher : rediriger d'abord puis corriger un instant plus tard ferait
 *    clignoter l'écran de connexion pour un utilisateur déjà connecté.
 * 2. Non connecté -> /connexion, en mémorisant la page demandée (`from`)
 *    pour y revenir après l'OTP.
 * 3. Connecté avec un rôle non autorisé -> refus propre (RoleRestricted),
 *    jamais l'écran d'un autre rôle. Le backend refuse déjà les données
 *    (403) : le front s'aligne pour ne pas afficher d'écran hors sujet.
 */
export function ProtectedRoute({ children, roles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, role } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <PageLoader />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/connexion" state={{ from: location }} replace />;
  }

  if (roles && !roles.some((allowed) => allowed === role)) {
    return <RoleRestricted reservedFor={roles[0]} currentRole={role} />;
  }

  return <>{children}</>;
}
