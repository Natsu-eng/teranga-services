export interface Coordinates {
  lat: number;
  lng: number;
}

// Le Plateau, Dakar — repère par défaut tant que la sélection de quartier
// (LocationPicker.tsx) n'est pas reliée à de vraies coordonnées (BUILD_PLAN.md §5 :
// "aujourd'hui simulé par un sélecteur de quartier"). Utilisé uniquement en
// secours (permission refusée, navigateur sans géolocalisation, timeout) —
// jamais un échec bloquant.
const FALLBACK_POSITION: Coordinates = { lat: 14.6937, lng: -17.4441 };
const GEOLOCATION_TIMEOUT_MS = 5_000;

/**
 * Résout la position courante du visiteur. Ne rejette jamais : une
 * permission refusée, un navigateur sans `navigator.geolocation`, ou un
 * timeout résolvent tous silencieusement vers `FALLBACK_POSITION` plutôt que
 * de bloquer un parcours (créer une demande) sur un aléa de géolocalisation.
 */
export function getCurrentPosition(): Promise<Coordinates> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve(FALLBACK_POSITION);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => resolve(FALLBACK_POSITION),
      { timeout: GEOLOCATION_TIMEOUT_MS },
    );
  });
}
