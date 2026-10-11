import { useCallback } from 'react';
import { useNavigate } from 'react-router';

/**
 * Retour arrière robuste pour les en-têtes de sous-page (AppBar).
 *
 * `navigate(-1)` seul est piégeux : sur un lien profond (onglet ouvert
 * directement sur /artisans/123), il n'y a pas de page précédente DANS
 * l'app et l'utilisateur serait renvoyé hors du site. React Router
 * mémorise la position dans `history.state.idx` : s'il existe une entrée
 * antérieure dans l'app, on y revient ; sinon on va à `fallback`.
 */
export function useBackNavigation(fallback: string): () => void {
  const navigate = useNavigate();

  return useCallback(() => {
    const idx = (window.history.state as { idx?: unknown } | null)?.idx;
    if (typeof idx === 'number' && idx > 0) {
      navigate(-1);
    } else {
      navigate(fallback, { replace: true });
    }
  }, [navigate, fallback]);
}
