import { useState } from 'react';
import { ApiError, api } from '../../../lib/api';

/**
 * Optimistic PATCH /artisans/me { is_available } (BUILD_PLAN.md §3.2):
 * the caller applies the flip immediately (`applyOptimistic`) for instant
 * visual feedback, then this hook confirms it against the backend and
 * reverts (`applyOptimistic(current)`) if the call fails — the source of
 * truth stays wherever the caller already holds the artisan profile
 * (`useArtisan`'s `setData`), no parallel state duplicated here.
 */
export function useAvailabilityToggle() {
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle(current: boolean, applyOptimistic: (next: boolean) => void): Promise<void> {
    const next = !current;
    setError(null);
    applyOptimistic(next);
    setIsSaving(true);
    try {
      await api.updateArtisanAvailability(next);
    } catch (err) {
      applyOptimistic(current);
      setError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
    } finally {
      setIsSaving(false);
    }
  }

  return { isSaving, error, toggle };
}
