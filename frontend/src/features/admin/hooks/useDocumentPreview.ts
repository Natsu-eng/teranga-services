import { useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../../../lib/api';

interface PreviewState {
  url: string;
  isPdf: boolean;
}

function toMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.';
}

/**
 * Chargement à la demande du binaire d'un document (BUILD_PLAN.md, espace
 * admin) : jamais un `<img src="...">` direct sur l'endpoint (qui exige un
 * `Authorization: Bearer`, qu'un tag `<img>` ne peut pas porter) -- on
 * récupère le `Blob` via `apiRequestBlob` puis on construit une URL locale
 * (`URL.createObjectURL`), révoquée au démontage pour ne pas fuiter de
 * mémoire ni laisser une donnée sensible adressable plus longtemps que
 * nécessaire.
 */
export function useDocumentPreview() {
  const [previews, setPreviews] = useState<Record<string, PreviewState>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Le ref n'est jamais lu ni écrit pendant le rendu (interdit par
  // react-hooks/refs) : uniquement synchronisé après coup dans un effet, et
  // lu uniquement dans le nettoyage au démontage ci-dessous.
  const previewsRef = useRef(previews);
  useEffect(() => {
    previewsRef.current = previews;
  }, [previews]);

  useEffect(
    () => () => {
      Object.values(previewsRef.current).forEach(({ url }) => URL.revokeObjectURL(url));
    },
    [],
  );

  async function load(verificationId: string): Promise<void> {
    if (previews[verificationId]) return;
    setError(null);
    setLoadingId(verificationId);
    try {
      const blob = await api.getAdminVerificationDocumentBlob(verificationId);
      const url = URL.createObjectURL(blob);
      setPreviews((prev) => ({ ...prev, [verificationId]: { url, isPdf: blob.type === 'application/pdf' } }));
    } catch (err) {
      setError(toMessage(err));
    } finally {
      setLoadingId(null);
    }
  }

  return { previews, loadingId, error, load };
}
