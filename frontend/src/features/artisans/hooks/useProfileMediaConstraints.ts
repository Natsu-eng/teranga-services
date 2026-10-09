import { useEffect } from 'react';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';
import type { ProfileMediaConstraints } from '../../../types';

/**
 * Contraintes d'envoi des photos du profil, telles que le backend les
 * applique (seule source de vérité, voir features/artisans/profileMedia.ts).
 * `enabled` à false (pas encore d'artisan connecté) : aucun appel.
 * En cas d'échec, `data` reste `null` : le pré-contrôle local se désactive
 * et le serveur tranche seul -- jamais de plafond deviné côté client.
 */
export function useProfileMediaConstraints(enabled: boolean) {
  const { data, run } = useAsyncResource<ProfileMediaConstraints>();

  useEffect(() => {
    if (enabled) run(() => api.getProfileMediaConstraints());
  }, [enabled, run]);

  return data ?? null;
}
