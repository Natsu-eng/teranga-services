import { useEffect } from 'react';
import type { ArtisanZone } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

/** `GET /artisans/me/zone` — zone d'intervention retenue par le serveur
 * (source, quartier, rayon par métier) et changements encore possibles.
 * `enabled` : en attente tant que le compte artisan n'est pas confirmé. */
export function useMyArtisanZone(enabled: boolean) {
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<ArtisanZone>();

  useEffect(() => {
    if (!enabled) return;
    run(() => api.getMyArtisanZone());
  }, [run, enabled]);

  return { data, isLoading, error, reload, setData };
}
