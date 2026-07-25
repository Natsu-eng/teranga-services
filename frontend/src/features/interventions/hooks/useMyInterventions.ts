import { useEffect } from 'react';
import type { Intervention } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

// Adapts to the caller's role server-side (GET /interventions/me, Lot 12a):
// a client sees their own interventions, an artisan sees the ones assigned
// to them -- same hook, same endpoint, for both InterventionsScreen renders.
export function useMyInterventions() {
  const { data, isLoading, error, run, reload } = useAsyncResource<Intervention[]>();

  useEffect(() => {
    run(() => api.listMyInterventions());
  }, [run]);

  return { data, isLoading, error, reload };
}
