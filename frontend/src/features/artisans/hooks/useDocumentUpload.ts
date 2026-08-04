import { useState } from 'react';
import { ApiError, api } from '../../../lib/api';
import type { VerificationDocType } from '../../../types';

interface UploadState {
  isUploading: boolean;
  error: string | null;
}

const IDLE_STATE: UploadState = { isUploading: false, error: null };

/**
 * État d'upload par type de document (CNI et selfie peuvent être envoyés
 * indépendamment, en même temps). `onUploaded` est appelé sans argument en
 * cas de succès : le backend recalcule `verified_status` côté serveur à
 * chaque upload (app.services.documents), donc l'appelant recharge la liste
 * de vérification (`useMyVerification().reload`) plutôt que de la corriger
 * localement -- évite que la liste et le statut dérivé ne divergent jamais.
 */
export function useDocumentUpload(onUploaded: () => void) {
  const [stateByType, setStateByType] = useState<Partial<Record<VerificationDocType, UploadState>>>(
    {},
  );

  async function upload(docType: VerificationDocType, file: File): Promise<void> {
    setStateByType((prev) => ({ ...prev, [docType]: { isUploading: true, error: null } }));
    try {
      await api.uploadVerificationDocument(docType, file);
      setStateByType((prev) => ({ ...prev, [docType]: IDLE_STATE }));
      onUploaded();
    } catch (err) {
      setStateByType((prev) => ({
        ...prev,
        [docType]: {
          isUploading: false,
          error: err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
        },
      }));
    }
  }

  function stateFor(docType: VerificationDocType): UploadState {
    return stateByType[docType] ?? IDLE_STATE;
  }

  return { upload, stateFor };
}
