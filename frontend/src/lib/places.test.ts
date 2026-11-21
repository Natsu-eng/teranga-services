import { describe, expect, it } from 'vitest';
import { TEST_CATALOG } from '../testing/neighborhoodCatalog';
import {
  distanceFromRegionCenterKm,
  distanceKm,
  findNeighborhood,
  groupByDepartment,
  isInServiceRegion,
  neighborhoodPlace,
} from './places';

const region = TEST_CATALOG.serviceRegion;

describe('places (calculs, sans liste locale)', () => {
  it('résout un quartier par identifiant, alias historiques compris', () => {
    expect(findNeighborhood(TEST_CATALOG, 'medina')?.label).toBe('Médina');
    // Anciens identifiants gardés par des téléphones.
    expect(findNeighborhood(TEST_CATALOG, 'almadies')?.id).toBe('ngor');
    expect(findNeighborhood(TEST_CATALOG, 'yoff-ngor')?.id).toBe('yoff');
    expect(findNeighborhood(TEST_CATALOG, 'inconnu')).toBeUndefined();
    expect(findNeighborhood(TEST_CATALOG, null)).toBeUndefined();
  });

  it('un lieu de quartier porte le centre officiel du quartier', () => {
    const medina = findNeighborhood(TEST_CATALOG, 'medina')!;
    expect(neighborhoodPlace(medina)).toEqual({
      kind: 'quartier',
      neighborhoodId: 'medina',
      label: 'Médina',
      lat: medina.lat,
      lng: medina.lng,
    });
  });

  it('regroupe par département dans l’ordre reçu du serveur', () => {
    const groups = groupByDepartment(TEST_CATALOG.items);
    expect(groups.map((group) => group.label)).toEqual(['Dakar', 'Rufisque']);
    expect(groups[1].items.map((item) => item.id)).toEqual(['bargny']);
  });

  it('mesure les distances et la région desservie reçue du serveur', () => {
    const plateau = findNeighborhood(TEST_CATALOG, 'plateau')!;
    const ouakam = findNeighborhood(TEST_CATALOG, 'ouakam')!;
    expect(Math.round(distanceKm(plateau, ouakam))).toBe(8);
    for (const neighborhood of TEST_CATALOG.items) {
      expect(isInServiceRegion(neighborhood, region)).toBe(true);
    }
    // Paris : hors région.
    expect(isInServiceRegion({ lat: 48.9097, lng: 2.3819 }, region)).toBe(false);
    expect(distanceFromRegionCenterKm(region.center, region)).toBe(0);
  });
});
