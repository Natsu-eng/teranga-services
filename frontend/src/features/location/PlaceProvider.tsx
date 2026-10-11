import React, { useCallback, useMemo, useState } from 'react';
import {
  DEFAULT_NEIGHBORHOOD_ID,
  findNeighborhood,
  neighborhoodPlace,
  type Place,
} from '../../lib/places';
import { PlaceContext, type PlaceContextValue } from './place-context';

/** Mémoire du quartier choisi, propre à ce navigateur (simple confort). */
export const PLACE_STORAGE_KEY = 'teranga.quartier';

function readStoredNeighborhoodId(): string {
  try {
    const stored = window.localStorage.getItem(PLACE_STORAGE_KEY);
    return findNeighborhood(stored) ? (stored as string) : DEFAULT_NEIGHBORHOOD_ID;
  } catch {
    // Stockage indisponible (navigation privée, blocage) : quartier par défaut.
    return DEFAULT_NEIGHBORHOOD_ID;
  }
}

function storeNeighborhoodId(id: string): void {
  try {
    window.localStorage.setItem(PLACE_STORAGE_KEY, id);
  } catch {
    // Sans stockage, le choix vaut pour la session en cours seulement.
  }
}

/**
 * Lieu d'intervention partagé par toute l'application : le quartier de
 * l'en-tête et le lieu d'une nouvelle demande sont la MÊME valeur — ils ne
 * peuvent plus se contredire.
 *
 * Seul un quartier est mémorisé (identifiant, jamais de coordonnées
 * personnelles) ; une position GPS acceptée par le client ne vit qu'en
 * mémoire, le temps de la session.
 */
export const PlaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [place, setPlaceState] = useState<Place>(() =>
    neighborhoodPlace(readStoredNeighborhoodId()),
  );

  const setPlace = useCallback((next: Place) => {
    setPlaceState(next);
    if (next.kind === 'quartier') storeNeighborhoodId(next.neighborhoodId);
  }, []);

  const value = useMemo<PlaceContextValue>(() => ({ place, setPlace }), [place, setPlace]);
  return <PlaceContext.Provider value={value}>{children}</PlaceContext.Provider>;
};
