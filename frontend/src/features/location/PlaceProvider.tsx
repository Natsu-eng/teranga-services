import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '../../lib/api';
import { fetchNeighborhoods } from '../../lib/api/neighborhoods';
import {
  findNeighborhood,
  neighborhoodPlace,
  type NeighborhoodCatalog,
  type Place,
} from '../../lib/places';
import { PlaceContext, type PlaceContextValue } from './place-context';

/** Mémoire du quartier choisi, propre à ce navigateur (simple confort). */
export const PLACE_STORAGE_KEY = 'teranga.quartier';

function readStoredNeighborhoodId(): string | null {
  try {
    return window.localStorage.getItem(PLACE_STORAGE_KEY);
  } catch {
    // Stockage indisponible (navigation privée, blocage) : quartier par défaut.
    return null;
  }
}

function storeNeighborhoodId(id: string): void {
  try {
    window.localStorage.setItem(PLACE_STORAGE_KEY, id);
  } catch {
    // Sans stockage, le choix vaut pour la session en cours seulement.
  }
}

/** Le quartier mémorisé (alias historique résolu), sinon celui par défaut du serveur. */
function initialPlace(catalog: NeighborhoodCatalog): Place | null {
  const neighborhood =
    findNeighborhood(catalog, readStoredNeighborhoodId()) ??
    findNeighborhood(catalog, catalog.defaultId);
  return neighborhood ? neighborhoodPlace(neighborhood) : null;
}

/**
 * Lieu d'intervention partagé par toute l'application : le quartier de
 * l'en-tête et le lieu d'une nouvelle demande sont la MÊME valeur — ils ne
 * peuvent plus se contredire.
 *
 * La liste des quartiers vient du serveur (`GET /meta/neighborhoods`),
 * chargée une fois. Seul un identifiant de quartier est mémorisé (jamais de
 * coordonnées personnelles) ; un ancien identifiant gardé par le téléphone
 * (« almadies », « yoff-ngor ») est résolu par les alias du serveur. Une
 * position GPS acceptée par le client ne vit qu'en mémoire.
 *
 * `loadCatalog` : injectable pour les tests. `initialCatalog` : catalogue
 * déjà connu (tests) — aucune requête n'est alors faite.
 */
export const PlaceProvider: React.FC<{
  children: React.ReactNode;
  loadCatalog?: () => Promise<NeighborhoodCatalog>;
  initialCatalog?: NeighborhoodCatalog;
}> = ({ children, loadCatalog = fetchNeighborhoods, initialCatalog }) => {
  const [catalog, setCatalog] = useState<NeighborhoodCatalog | null>(initialCatalog ?? null);
  const [catalogError, setCatalogError] = useState<ApiError | null>(null);
  const [chosenPlace, setChosenPlace] = useState<Place | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (initialCatalog && attempt === 0) return;
    let ignore = false;
    loadCatalog()
      .then((loaded) => {
        if (ignore) return;
        setCatalog(loaded);
        setCatalogError(null);
      })
      .catch((err: unknown) => {
        if (ignore) return;
        setCatalogError(
          err instanceof ApiError
            ? err
            : new ApiError('unknown', "La liste des quartiers n'a pas pu être chargée."),
        );
      });
    return () => {
      ignore = true;
    };
  }, [loadCatalog, initialCatalog, attempt]);

  // Tant que le client n'a rien choisi : quartier mémorisé ou par défaut.
  const place = useMemo(
    () => chosenPlace ?? (catalog ? initialPlace(catalog) : null),
    [chosenPlace, catalog],
  );

  const setPlace = useCallback((next: Place) => {
    setChosenPlace(next);
    if (next.kind === 'quartier') storeNeighborhoodId(next.neighborhoodId);
  }, []);
  const reloadCatalog = useCallback(() => setAttempt((value) => value + 1), []);

  const value = useMemo<PlaceContextValue>(
    () => ({ place, setPlace, catalog, catalogError, reloadCatalog }),
    [place, setPlace, catalog, catalogError, reloadCatalog],
  );
  return <PlaceContext.Provider value={value}>{children}</PlaceContext.Provider>;
};
