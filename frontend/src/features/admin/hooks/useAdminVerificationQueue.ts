import { useCallback, useEffect } from 'react';
import type { AdminVerificationListItem } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

/** File d'attente des documents en attente de revue (BUILD_PLAN.md, espace
 * admin) -- toujours `status=pending` : c'est une file de travail, pas un
 * historique (pas de filtre par statut côté UI pour ce lot). */
export function useAdminVerificationQueue() {
  const { data, isLoading, error, run, reload, setData } =
    useAsyncResource<AdminVerificationListItem[]>();

  useEffect(() => {
    run(() => api.listAdminVerifications({ status: 'pending' }));
  }, [run]);

  const removeFromQueue = useCallback(
    (verificationId: string) => {
      setData((prev) => (prev ? prev.filter((item) => item.id !== verificationId) : prev));
    },
    [setData],
  );

  return { data, isLoading, error, reload, removeFromQueue };
}
