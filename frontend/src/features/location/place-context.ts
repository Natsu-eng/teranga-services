import { createContext } from 'react';
import type { ApiError } from '../../lib/api';
import type { NeighborhoodCatalog, Place } from '../../lib/places';

export interface PlaceContextValue {
  /**
   * Lieu d'intervention courant : affiché dans l'en-tête, proposé par défaut
   * aux demandes. `null` tant que la liste des quartiers n'est pas arrivée
   * du serveur (et que le client n'a pas accepté sa position GPS).
   */
  place: Place | null;
  setPlace: (place: Place) => void;
  /** Quartiers desservis et région, servis par le backend (aucune copie locale). */
  catalog: NeighborhoodCatalog | null;
  catalogError: ApiError | null;
  reloadCatalog: () => void;
}

export const DEFAULT_PLACE_CONTEXT: PlaceContextValue = {
  place: null,
  setPlace: () => undefined,
  catalog: null,
  catalogError: null,
  reloadCatalog: () => undefined,
};

export const PlaceContext = createContext<PlaceContextValue>(DEFAULT_PLACE_CONTEXT);
