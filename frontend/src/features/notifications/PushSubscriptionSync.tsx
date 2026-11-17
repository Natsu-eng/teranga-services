import React, { useEffect } from 'react';
import { api } from '../../lib/api';
import { browserPush, syncPushSubscription, type PushBrowser } from '../../lib/push/webPush';
import { useAuth } from '../auth/hooks/useAuth';

interface PushSubscriptionSyncProps {
  /** Injection pour les tests ; par défaut, le vrai navigateur. */
  browser?: PushBrowser;
}

/**
 * Resynchronise l'abonnement push de cet appareil à chaque ouverture de
 * session (compte client ou artisan), SI la permission est déjà accordée :
 * le serveur garde l'abonnement à jour et rattaché au compte connecté
 * (navigateur partagé, adresse renouvelée par le navigateur, clé changée).
 * Ne demande jamais la permission ; n'affiche rien.
 */
export const PushSubscriptionSync: React.FC<PushSubscriptionSyncProps> = ({ browser }) => {
  const auth = useAuth();
  const userId = auth.user?.id ?? null;
  const eligible = auth.isAuthenticated && (auth.role === 'client' || auth.role === 'artisan');

  useEffect(() => {
    if (!eligible || !userId) return;
    syncPushSubscription(api, browser ?? browserPush()).catch((error: unknown) => {
      // Jamais bloquant : l'app fonctionne, les notifications reprendront
      // à la prochaine ouverture.
      console.warn('Notifications push : abonnement non resynchronisé.', error);
    });
  }, [eligible, userId, browser]);

  return null;
};
