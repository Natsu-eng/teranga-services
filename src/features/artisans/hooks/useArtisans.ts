import { useEffect } from 'react';
import type { Artisan } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

export function useArtisans() {
  const { data, isLoading, error, run, reload } = useAsyncResource<Artisan[]>();

  useEffect(() => {
    run(() => api.listArtisans());
  }, [run]);

  return { data, isLoading, error, reload };
}
