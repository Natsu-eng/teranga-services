import { useEffect } from 'react';
import type { Artisan } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

export function useArtisan(id: string) {
  const { data, isLoading, error, run, reload } = useAsyncResource<Artisan>();

  useEffect(() => {
    run(() => api.getArtisanById(id));
  }, [run, id]);

  return { data, isLoading, error, reload };
}
