import React from 'react';
import { ComingSoon } from '../../components/ui/ComingSoon';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';

/**
 * Messagerie : le backend ne sert pas encore de conversations
 * (AUDIT_PHASE2.md §7). Écran d'attente honnête, avec un retour vers
 * l'accueil propre au rôle (tableau de bord pour un artisan).
 */
export const MessagesScreen: React.FC = () => {
  const auth = useAuth();
  const isPro = toDisplayRole(auth.role) === 'artisan';

  return (
    <ComingSoon
      title="La messagerie arrive bientôt"
      description="Les échanges avec les artisans depuis l'application seront bientôt disponibles."
      backTo={isPro ? '/pro' : '/accueil'}
      backLabel={isPro ? 'Retour au tableau de bord' : undefined}
    />
  );
};
