import { createContext } from 'react';
import { DEFAULT_NEIGHBORHOOD_ID, neighborhoodPlace, type Place } from '../../lib/places';

export interface PlaceContextValue {
  /** Lieu d'intervention courant : affiché dans l'en-tête, proposé par défaut aux demandes. */
  place: Place;
  setPlace: (place: Place) => void;
}

export const DEFAULT_PLACE_CONTEXT: PlaceContextValue = {
  place: neighborhoodPlace(DEFAULT_NEIGHBORHOOD_ID),
  setPlace: () => undefined,
};

export const PlaceContext = createContext<PlaceContextValue>(DEFAULT_PLACE_CONTEXT);
