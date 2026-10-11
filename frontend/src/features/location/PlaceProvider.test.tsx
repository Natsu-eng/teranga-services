import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { PlaceProvider, PLACE_STORAGE_KEY } from './PlaceProvider';
import { usePlace } from './usePlace';
import { neighborhoodPlace, positionPlace } from '../../lib/places';
function Probe() {
  const { place, setPlace } = usePlace();
  return (
    <>
      <p>Lieu : {place.label}</p>
      <button type="button" onClick={() => setPlace(neighborhoodPlace('yoff-ngor'))}>
        Choisir Yoff
      </button>
      <button type="button" onClick={() => setPlace(positionPlace({ lat: 14.7, lng: -17.45 }))}>
        Utiliser ma position
      </button>
    </>
  );
}

function renderProvider() {
  return render(
    <PlaceProvider>
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

  it('part du quartier par défaut', () => {
    renderProvider();

    expect(screen.getByText('Lieu : Dakar Plateau')).toBeInTheDocument();
  });

  it('mémorise le quartier choisi (identifiant seul) et le restaure', () => {
    const { unmount } = renderProvider();
    fireEvent.click(screen.getByRole('button', { name: 'Choisir Yoff' }));
    expect(window.localStorage.getItem(PLACE_STORAGE_KEY)).toBe('yoff-ngor');
    unmount();

    renderProvider();
    expect(screen.getByText('Lieu : Yoff - Ngor')).toBeInTheDocument();
  });

  it('ne mémorise jamais une position GPS (donnée personnelle)', () => {
    renderProvider();

    fireEvent.click(screen.getByRole('button', { name: 'Utiliser ma position' }));

    expect(screen.getByText('Lieu : Ma position actuelle')).toBeInTheDocument();
    expect(window.localStorage.getItem(PLACE_STORAGE_KEY)).toBeNull();
  });

  it('ignore une valeur mémorisée inconnue ou un stockage indisponible', () => {
    window.localStorage.setItem(PLACE_STORAGE_KEY, 'quartier-supprime');
    const { unmount } = renderProvider();
    expect(screen.getByText('Lieu : Dakar Plateau')).toBeInTheDocument();
    unmount();

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('stockage bloqué');
    });
    renderProvider();
    expect(screen.getByText('Lieu : Dakar Plateau')).toBeInTheDocument();
  });
});
