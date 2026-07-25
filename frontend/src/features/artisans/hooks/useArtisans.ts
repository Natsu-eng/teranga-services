import { useEffect } from 'react';
import type { Artisan } from '../../../types';
import { api } from '../../../lib/api';
import type { ArtisanFilters } from '../../../lib/api/types';
import { useAsyncResource } from '../../../lib/useAsyncResource';

// `filters` must be a stable reference across renders when a caller needs
// server-side filtering (e.g. SearchScreen memoizes it from URL params) —
// left `undefined` by callers that just want the default unfiltered list.
export function useArtisans(filters?: ArtisanFilters) {
  const { data, isLoading, error, run, reload } = useAsyncResource<Artisan[]>();

  useEffect(() => {
    run(() => api.listArtisans(filters));
  }, [run, filters]);

  return { data, isLoading, error, reload };
}
