import { useEffect } from 'react';
import type { MyVerification } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

/** `GET /artisans/me/documents` — statut de vérification et métadonnées des
 * documents de l'artisan (jamais le contenu binaire). `enabled` reprend le
 * pattern "id pas encore connu" de `useArtisan` : reste en attente tant que
 * l'appelant ne sait pas encore s'il s'agit bien d'un compte artisan. */
export function useMyVerification(enabled: boolean) {
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<MyVerification>();

  useEffect(() => {
    if (!enabled) return;
    run(() => api.listMyVerificationDocuments());
  }, [run, enabled]);

  return { data, isLoading, error, reload, setData };
}
