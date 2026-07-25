import { useEffect } from 'react';
import type { Trade } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

export function useTrades() {
  const { data, isLoading, error, run, reload } = useAsyncResource<Trade[]>();

  useEffect(() => {
    run(() => api.listTrades());
  }, [run]);

  return { data, isLoading, error, reload };
}
