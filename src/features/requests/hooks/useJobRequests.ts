import { useCallback, useEffect } from 'react';
import type { JobRequest } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

export function useJobRequests() {
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<JobRequest[]>();

  useEffect(() => {
    run(() => api.listJobRequests());
  }, [run]);

  const acceptJob = useCallback(
    (jobId: string) => {
      setData(
        (prev) => prev?.map((job) => (job.id === jobId ? { ...job, status: 'accepted' } : job)) ?? prev,
      );
    },
    [setData],
  );

  return { data, isLoading, error, reload, acceptJob };
}
