import { useEffect } from 'react';
import type { Artisan } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

// Accepts a possibly-not-yet-known id (e.g. resolved asynchronously from
// useCurrentUser()): stays in a pending state until id is available.
export function useArtisan(id: string | null) {
  const { data, isLoading, error, run, reload } = useAsyncResource<Artisan>();

  useEffect(() => {
    if (!id) return;
    run(() => api.getArtisanById(id));
  }, [run, id]);

  return { data, isLoading, error, reload };
}
