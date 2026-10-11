import type { Coordinates } from './places';

export type { Coordinates } from './places';

const GEOLOCATION_TIMEOUT_MS = 5_000;
// Codes d'erreur de la spécification W3C (GeolocationPositionError) : pas
// de dépendance aux constantes de l'objet, absentes de certains environnements.
const PERMISSION_DENIED = 1;
const TIMEOUT = 3;

export type GeolocationFailure = 'unsupported' | 'denied' | 'unavailable' | 'timeout';

/** La position n'a pas pu être obtenue : l'écran le DIT, il ne devine pas. */
export class GeolocationError extends Error {
  readonly reason: GeolocationFailure;

  constructor(reason: GeolocationFailure) {
    super(GEOLOCATION_MESSAGES[reason]);
    this.name = 'GeolocationError';
    this.reason = reason;
  }
}

export const GEOLOCATION_MESSAGES: Record<GeolocationFailure, string> = {
  unsupported: "Votre navigateur ne permet pas d'obtenir votre position.",
  denied: "L'accès à votre position a été refusé.",
  unavailable: "Votre position n'a pas pu être déterminée.",
  timeout: 'La recherche de votre position a pris trop de temps.',
};

/**
 * Demande la position du navigateur — uniquement à l'initiative de
 * l'utilisateur (bouton « Utiliser ma position actuelle »), qui voit
 * ensuite le résultat avant qu'il ne serve.
 *
 * Rejette avec une `GeolocationError` explicite en cas d'échec. Il n'y a
 * plus de position de repli silencieuse : un repli invisible (l'ancien
 * comportement) faisait passer un lieu qui n'était pas celui du client.
 */
export function getCurrentPosition(): Promise<Coordinates> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new GeolocationError('unsupported'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      (error) =>
        reject(
          new GeolocationError(
            error.code === PERMISSION_DENIED
              ? 'denied'
              : error.code === TIMEOUT
                ? 'timeout'
                : 'unavailable',
          ),
        ),
      { timeout: GEOLOCATION_TIMEOUT_MS },
    );
  });
}
