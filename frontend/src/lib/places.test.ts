import { describe, expect, it } from 'vitest';
import {
  DEFAULT_NEIGHBORHOOD_ID,
  NEIGHBORHOODS,
  SERVICE_REGION_RADIUS_KM,
  distanceFromDakarKm,
  distanceKm,
  isInServiceRegion,
  neighborhoodPlace,
  positionPlace,
} from './places';

describe('places', () => {
  it('a des quartiers aux identifiants uniques, tous dans la région de Dakar', () => {
    expect(new Set(NEIGHBORHOODS.map((n) => n.id)).size).toBe(NEIGHBORHOODS.length);
    for (const neighborhood of NEIGHBORHOODS) {
      expect(isInServiceRegion(neighborhood)).toBe(true);
      expect(distanceFromDakarKm(neighborhood)).toBeLessThan(SERVICE_REGION_RADIUS_KM);
    }
  });

  it('mesure des distances réalistes', () => {
    const plateau = neighborhoodPlace('plateau');
    const ouakam = neighborhoodPlace('ouakam');

    expect(Math.round(distanceKm(plateau, ouakam))).toBe(8);
    // La situation observée en test manuel : une position en région parisienne.
    expect(distanceFromDakarKm({ lat: 48.9097, lng: 2.3819 })).toBeGreaterThan(4_000);
    expect(isInServiceRegion({ lat: 48.9097, lng: 2.3819 })).toBe(false);
  });

  it('construit un lieu de quartier avec ses coordonnées, et retombe sur le défaut si inconnu', () => {
    expect(neighborhoodPlace('almadies')).toEqual({
      kind: 'quartier',
      neighborhoodId: 'almadies',
      label: 'Almadies, Dakar',
      lat: 14.7419,
      lng: -17.508,
    });
    expect(neighborhoodPlace('inconnu').neighborhoodId).toBe(DEFAULT_NEIGHBORHOOD_ID);
  });

  it('étiquette une position acceptée par le client', () => {
    expect(positionPlace({ lat: 14.7, lng: -17.45 })).toEqual({
      kind: 'position',
      label: 'Ma position actuelle',
      lat: 14.7,
      lng: -17.45,
    });
  });
});
