/**
 * Lieux d'intervention (lot `fix/localisation-demande`).
 *
 * Source unique des quartiers proposés partout (sélecteur de l'en-tête,
 * écran de demande) : un quartier choisi dans l'en-tête et le lieu d'une
 * demande ne peuvent donc plus se contredire.
 *
 * Coordonnées : centre approximatif de chaque quartier (relevé sur
 * OpenStreetMap), précision de l'ordre de quelques centaines de mètres —
 * suffisante pour la règle de zone, dont les rayons se comptent en
 * kilomètres. Le client choisit toujours ce qui est envoyé : rien n'est
 * deviné à sa place.
 */

export interface Coordinates {
  lat: number;
  lng: number;
}

export interface Neighborhood extends Coordinates {
  id: string;
  label: string;
}

export const NEIGHBORHOODS: readonly Neighborhood[] = [
  { id: 'plateau', label: 'Dakar Plateau', lat: 14.6681, lng: -17.4339 },
  { id: 'almadies', label: 'Almadies, Dakar', lat: 14.7419, lng: -17.508 },
  { id: 'ouakam', label: 'Ouakam, Dakar', lat: 14.7225, lng: -17.4878 },
  { id: 'mermoz-sacre-coeur', label: 'Mermoz - Sacré Cœur', lat: 14.712, lng: -17.469 },
  { id: 'yoff-ngor', label: 'Yoff - Ngor', lat: 14.753, lng: -17.49 },
  { id: 'point-e', label: 'Point E, Dakar', lat: 14.6951, lng: -17.4593 },
] as const;

export const DEFAULT_NEIGHBORHOOD_ID = 'plateau';

/** Lieu d'intervention retenu : un quartier, ou la position que le client a acceptée. */
export type Place =
  | ({ kind: 'quartier'; neighborhoodId: string; label: string } & Coordinates)
  | ({ kind: 'position'; label: string } & Coordinates);

export type NeighborhoodPlace = Extract<Place, { kind: 'quartier' }>;

export const CURRENT_POSITION_LABEL = 'Ma position actuelle';

export function findNeighborhood(id: string | null | undefined): Neighborhood | undefined {
  return NEIGHBORHOODS.find((neighborhood) => neighborhood.id === id);
}

export function neighborhoodPlace(id: string): NeighborhoodPlace {
  const neighborhood = findNeighborhood(id) ?? findNeighborhood(DEFAULT_NEIGHBORHOOD_ID)!;
  return {
    kind: 'quartier',
    neighborhoodId: neighborhood.id,
    label: neighborhood.label,
    lat: neighborhood.lat,
    lng: neighborhood.lng,
  };
}

export function positionPlace(coordinates: Coordinates): Place {
  return { kind: 'position', label: CURRENT_POSITION_LABEL, ...coordinates };
}

/*
 * Région desservie, pour un AVERTISSEMENT d'affichage seulement (la règle
 * de zone, elle, est appliquée par le serveur artisan par artisan) : une
 * position à plus de 60 km du centre de Dakar sort de la région de Dakar,
 * où opèrent les artisans de Téranga.
 */
const SERVICE_REGION_CENTER = findNeighborhood(DEFAULT_NEIGHBORHOOD_ID)!;
export const SERVICE_REGION_RADIUS_KM = 60;

const EARTH_RADIUS_KM = 6_371;

/** Distance à vol d'oiseau (formule de haversine), en kilomètres. */
export function distanceKm(a: Coordinates, b: Coordinates): number {
  const toRad = (degrees: number) => (degrees * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

/** Distance au centre de Dakar, en km entiers. */
export function distanceFromDakarKm(coordinates: Coordinates): number {
  return Math.round(distanceKm(coordinates, SERVICE_REGION_CENTER));
}

export function isInServiceRegion(coordinates: Coordinates): boolean {
  return distanceKm(coordinates, SERVICE_REGION_CENTER) <= SERVICE_REGION_RADIUS_KM;
}
