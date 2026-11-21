import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ApiError } from '../../lib/api';
import { findNeighborhood, neighborhoodPlace, positionPlace } from '../../lib/places';
import { TEST_CATALOG, loadTestCatalog } from '../../testing/neighborhoodCatalog';
import { PlaceProvider, PLACE_STORAGE_KEY } from './PlaceProvider';
import { usePlace } from './usePlace';

function Probe() {
  const { place, setPlace, catalogError, reloadCatalog } = usePlace();
  return (
    <>
      <p>Lieu : {place ? place.label : 'inconnu'}</p>
      {catalogError && (
        <button type="button" onClick={reloadCatalog}>
          Réessayer
        </button>
      )}
      <button
        type="button"
        onClick={() => setPlace(neighborhoodPlace(findNeighborhood(TEST_CATALOG, 'yoff')!))}
      >
        Choisir Yoff
      </button>
      <button type="button" onClick={() => setPlace(positionPlace({ lat: 14.7, lng: -17.45 }))}>
        Utiliser ma position
      </button>
    </>
  );
}

function renderProvider(loadCatalog = loadTestCatalog) {
  return render(
    <PlaceProvider loadCatalog={loadCatalog}>
      <Probe />
    </PlaceProvider>,
  );
}

describe('PlaceProvider', () => {
  beforeEach(() => window.localStorage.removeItem(PLACE_STORAGE_KEY));
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('attend la liste du serveur, puis part du quartier par défaut qu’il indique', async () => {
    renderProvider();

    expect(screen.getByText('Lieu : inconnu')).toBeInTheDocument();
    expect(await screen.findByText('Lieu : Dakar-Plateau')).toBeInTheDocument();
  });

  it('mémorise le quartier choisi (identifiant seul) et le restaure', async () => {
    const { unmount } = renderProvider();
    await screen.findByText('Lieu : Dakar-Plateau');
    fireEvent.click(screen.getByRole('button', { name: 'Choisir Yoff' }));
    expect(window.localStorage.getItem(PLACE_STORAGE_KEY)).toBe('yoff');
    unmount();

    renderProvider();
    expect(await screen.findByText('Lieu : Yoff')).toBeInTheDocument();
  });

  it('un ancien identifiant gardé par le téléphone retrouve sa commune', async () => {
    window.localStorage.setItem(PLACE_STORAGE_KEY, 'almadies');

    renderProvider();

    expect(await screen.findByText('Lieu : Ngor')).toBeInTheDocument();
  });

  it('ne mémorise jamais une position GPS (donnée personnelle)', async () => {
    renderProvider();
    await screen.findByText('Lieu : Dakar-Plateau');

    fireEvent.click(screen.getByRole('button', { name: 'Utiliser ma position' }));

    expect(screen.getByText('Lieu : Ma position actuelle')).toBeInTheDocument();
    expect(window.localStorage.getItem(PLACE_STORAGE_KEY)).toBeNull();
  });

  it('ignore une valeur mémorisée inconnue ou un stockage indisponible', async () => {
    window.localStorage.setItem(PLACE_STORAGE_KEY, 'quartier-supprime');
    const { unmount } = renderProvider();
    expect(await screen.findByText('Lieu : Dakar-Plateau')).toBeInTheDocument();
    unmount();

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('stockage bloqué');
    });
    renderProvider();
    expect(await screen.findByText('Lieu : Dakar-Plateau')).toBeInTheDocument();
  });

  it('un échec du chargement se dit et se réessaie, sans lieu inventé', async () => {
    const load = vi.fn(async () => {
      throw new ApiError('network', 'Serveur injoignable.');
    });
    renderProvider(load);

    fireEvent.click(await screen.findByRole('button', { name: 'Réessayer' }));

    expect(screen.getByText('Lieu : inconnu')).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
