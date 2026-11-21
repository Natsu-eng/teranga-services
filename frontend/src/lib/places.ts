/**
 * Lieux d'intervention : types et calculs, SANS aucune liste de quartiers.
 *
 * La liste fermée des quartiers (une entrée par commune de la région de
 * Dakar, centres tirés d'OpenStreetMap) vit côté serveur
 * (backend/app/core/neighborhoods.py) et arrive par
 * `GET /api/v1/meta/neighborhoods` (lib/api/neighborhoods.ts), avec la
 * région desservie. Le front n'en garde aucune copie : un quartier ajouté ou
 * corrigé côté serveur l'est partout à la fois.
 */

export interface Coordinates {
  lat: number;
  lng: number;
}

export interface Neighborhood extends Coordinates {
  id: string;
  label: string;
  /** Nom de la commune dans OpenStreetMap. */
  commune: string;
  department: string;
  departmentLabel: string;
}

/** Cercle hors duquel une position est hors de la région desservie. */
export interface ServiceRegion {
  center: Coordinates;
  radiusM: number;
}

export interface NeighborhoodCatalog {
  items: readonly Neighborhood[];
  /** Anciens identifiants (gardés sur des téléphones) -> identifiant actuel. */
  aliases: Readonly<Record<string, string>>;
  /** Quartier proposé tant que le client n'en a choisi aucun. */
  defaultId: string;
  serviceRegion: ServiceRegion;
}

/** Lieu d'intervention retenu : un quartier, ou la position que le client a acceptée. */
export type Place =
  | ({ kind: 'quartier'; neighborhoodId: string; label: string } & Coordinates)
  | ({ kind: 'position'; label: string } & Coordinates);

export type NeighborhoodPlace = Extract<Place, { kind: 'quartier' }>;

export const CURRENT_POSITION_LABEL = 'Ma position actuelle';

/** Le quartier de cet identifiant, alias historiques compris. */
export function findNeighborhood(
  catalog: NeighborhoodCatalog,
  id: string | null | undefined,
): Neighborhood | undefined {
  if (!id) return undefined;
  const canonical = catalog.aliases[id] ?? id;
  return catalog.items.find((neighborhood) => neighborhood.id === canonical);
}

export function neighborhoodPlace(neighborhood: Neighborhood): NeighborhoodPlace {
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

/** Quartiers regroupés par département, dans l'ordre reçu du serveur. */
export function groupByDepartment(
  items: readonly Neighborhood[],
): { label: string; items: Neighborhood[] }[] {
  const groups: { label: string; items: Neighborhood[] }[] = [];
  for (const neighborhood of items) {
    const group = groups.find((candidate) => candidate.label === neighborhood.departmentLabel);
    if (group) group.items.push(neighborhood);
    else groups.push({ label: neighborhood.departmentLabel, items: [neighborhood] });
  }
  return groups;
}

// Rayon moyen de la Terre (IUGG), comme le serveur (app/core/geo_privacy.py).
const EARTH_RADIUS_KM = 6_371.0088;

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

/** Distance au centre de la région desservie, en km entiers. */
export function distanceFromRegionCenterKm(
  coordinates: Coordinates,
  region: ServiceRegion,
): number {
  return Math.round(distanceKm(coordinates, region.center));
}

/**
 * Dans la région desservie ? AVERTISSEMENT d'affichage seulement : le
 * serveur applique lui-même la règle (refus d'une position GPS d'artisan
 * hors région, zone de chaque artisan pour une demande).
 */
export function isInServiceRegion(coordinates: Coordinates, region: ServiceRegion): boolean {
  return distanceKm(coordinates, region.center) * 1000 <= region.radiusM;
}
