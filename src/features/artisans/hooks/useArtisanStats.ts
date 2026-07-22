import { useEffect } from 'react';
import type { ArtisanStats } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

export function useArtisanStats(artisanId: string) {
  const { data, isLoading, error, run, reload } = useAsyncResource<ArtisanStats>();

  useEffect(() => {
    run(() => api.getArtisanStats(artisanId));
  }, [run, artisanId]);

  return { data, isLoading, error, reload };
}
