import { useEffect } from 'react';
import type { MyArtisanProfile } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

/** Vue de son propre profil (bio, métiers avec leurs id, statut de
 * vérification) — plus riche que `useArtisan` (vue publique), utilisé par
 * l'écran d'onboarding et le dashboard `/pro` pour décider quel état
 * afficher. */
export function useMyArtisanProfile(artisanId: string | null) {
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<MyArtisanProfile>();

  useEffect(() => {
    if (!artisanId) return;
    run(() => api.getMyArtisanProfile(artisanId));
  }, [run, artisanId]);

  return { data, isLoading, error, reload, setData };
}
