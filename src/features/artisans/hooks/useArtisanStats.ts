import { useEffect } from 'react';
import type { ArtisanStats } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

// Accepts a possibly-not-yet-known id (e.g. resolved asynchronously from
// useCurrentUser()): stays in a pending state until artisanId is available.
export function useArtisanStats(artisanId: string | null) {
  const { data, isLoading, error, run, reload } = useAsyncResource<ArtisanStats>();

  useEffect(() => {
    if (!artisanId) return;
    run(() => api.getArtisanStats(artisanId));
  }, [run, artisanId]);

  return { data, isLoading, error, reload };
}
