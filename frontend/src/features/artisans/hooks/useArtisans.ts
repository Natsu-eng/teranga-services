import { useEffect } from 'react';
import type { Artisan } from '../../../types';
import { api } from '../../../lib/api';
import type { ArtisanFilters } from '../../../lib/api/types';
import { useAsyncResource } from '../../../lib/useAsyncResource';

interface UseArtisansOptions {
  /**
   * `false` : aucun appel tant que la condition n'est pas remplie (ex. la
   * demande IA n'a pas encore détecté de métier). Défaut : `true`.
   */
  enabled?: boolean;
}

// `filters` must be a stable reference across renders when a caller needs
// server-side filtering (e.g. SearchScreen memoizes it from URL params) —
// left `undefined` by callers that just want the default unfiltered list.
export function useArtisans(filters?: ArtisanFilters, options: UseArtisansOptions = {}) {
  const { enabled = true } = options;
  const { data, isLoading, error, run, reload } = useAsyncResource<Artisan[]>();

  useEffect(() => {
    if (!enabled) return;
    run(() => api.listArtisans(filters));
  }, [run, filters, enabled]);

  return { data, isLoading, error, reload };
}
