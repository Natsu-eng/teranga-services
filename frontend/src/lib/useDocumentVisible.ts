import { useEffect, useState } from 'react';

function isVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

/**
 * Vrai tant que l'onglet est affiché. Sert à ne rien faire en arrière-plan :
 * connexion temps réel fermée et relectures suspendues quand l'onglet est
 * masqué (batterie, données mobiles, charge serveur), reprise au retour.
 */
export function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(isVisible);

  useEffect(() => {
    const handleChange = () => setVisible(isVisible());
    document.addEventListener('visibilitychange', handleChange);
    return () => document.removeEventListener('visibilitychange', handleChange);
  }, []);

  return visible;
}
