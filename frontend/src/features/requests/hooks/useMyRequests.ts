import { useEffect } from 'react';
import type { ServiceRequest } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

export function useMyRequests() {
  const { data, isLoading, error, run, reload } = useAsyncResource<ServiceRequest[]>();

  useEffect(() => {
    run(() => api.listMyServiceRequests());
  }, [run]);

  return { data, isLoading, error, reload };
}
