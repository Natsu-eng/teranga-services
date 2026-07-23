import { useEffect } from 'react';
import type { CurrentUser } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

export function useCurrentUser() {
  const { data, isLoading, error, run, reload } = useAsyncResource<CurrentUser>();

  useEffect(() => {
    run(() => api.getCurrentUser());
  }, [run]);

  return { data, isLoading, error, reload };
}
