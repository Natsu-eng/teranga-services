import { useState } from 'react';
import { ApiError, api } from '../../../lib/api';
import type { AdminVerificationReview } from '../../../types';

function toMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.';
}

interface PendingAction {
  verificationId: string;
  kind: 'approve' | 'reject';
}

/** Approuver/rejeter un document (BUILD_PLAN.md, espace admin) --
 * `onReviewed` retire l'élément traité de la file d'attente affichée. */
export function useVerificationReview(onReviewed: (verificationId: string) => void) {
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function approve(verificationId: string): Promise<AdminVerificationReview | null> {
    setError(null);
    setPendingAction({ verificationId, kind: 'approve' });
    try {
      const result = await api.approveVerification(verificationId);
      onReviewed(verificationId);
      return result;
    } catch (err) {
      setError(toMessage(err));
      return null;
    } finally {
      setPendingAction(null);
    }
  }

  async function reject(
    verificationId: string,
    note: string,
  ): Promise<AdminVerificationReview | null> {
    setError(null);
    setPendingAction({ verificationId, kind: 'reject' });
    try {
      const result = await api.rejectVerification(verificationId, note);
      onReviewed(verificationId);
      return result;
    } catch (err) {
      setError(toMessage(err));
      return null;
    } finally {
      setPendingAction(null);
    }
  }

  return { approve, reject, pendingAction, error };
}
