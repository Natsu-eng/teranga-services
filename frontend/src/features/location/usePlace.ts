import { useContext } from 'react';
import { PlaceContext, type PlaceContextValue } from './place-context';

/** Lieu d'intervention courant (voir PlaceProvider). */
export function usePlace(): PlaceContextValue {
  return useContext(PlaceContext);
}
