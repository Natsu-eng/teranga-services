import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { SearchScreen } from './SearchScreen';
import { useArtisans } from './hooks/useArtisans';
import { useTrades } from './hooks/useTrades';

vi.mock('./hooks/useArtisans');
vi.mock('./hooks/useTrades');

const mockedUseArtisans = vi.mocked(useArtisans);
const mockedUseTrades = vi.mocked(useTrades);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SearchScreen />
    </MemoryRouter>,
  );
}

describe('SearchScreen', () => {
  beforeEach(() => {
    mockedUseArtisans.mockReset();
    mockedUseArtisans.mockReturnValue({ data: [], isLoading: false, error: null, reload: vi.fn() });
    mockedUseTrades.mockReturnValue({
      data: [
        { id: 't1', code: 'plomberie', labelFr: 'Plomberie' },
        { id: 't2', code: 'electricite', labelFr: 'Électricité' },
      ],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  function lastFilters() {
    return mockedUseArtisans.mock.calls.at(-1)?.[0];
  }

  it('calls useArtisans with no filters when reached without query params', () => {
    renderAt('/recherche');

    expect(mockedUseArtisans).toHaveBeenCalledWith(undefined);
  });

  it('passes trade and near from the URL as server-side filters (from the /demande hand-off)', () => {
    renderAt('/recherche?trade=electricite&lat=14.7256&lng=-17.4914');

    expect(mockedUseArtisans).toHaveBeenCalledWith({
      trade: 'electricite',
      near: { lat: 14.7256, lng: -17.4914 },
    });
  });

  it('passes only the trade filter when no position is present', () => {
    renderAt('/recherche?trade=plomberie');

    expect(mockedUseArtisans).toHaveBeenCalledWith({ trade: 'plomberie', near: undefined });
  });

  describe('filtres serveur (plus aucun filtrage en mémoire)', () => {
    it('transmet la recherche libre et la note minimale lues dans l’URL', () => {
      renderAt('/recherche?q=fuite&note=4.5');

      expect(lastFilters()).toEqual({ search: 'fuite', minRating: 4.5 });
    });

    it('ignore une position invalide plutôt que d’envoyer NaN au serveur', () => {
      renderAt('/recherche?trade=plomberie&lat=abc&lng=-17.4');

      expect(lastFilters()).toEqual({ trade: 'plomberie' });
    });

    it('filtre par métier (code serveur) via les pastilles, état exposé par aria-pressed', () => {
      renderAt('/recherche');

      fireEvent.click(screen.getByRole('button', { name: 'Électricité' }));

      expect(lastFilters()).toEqual({ trade: 'electricite' });
      expect(screen.getByRole('button', { name: 'Électricité' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      expect(screen.getByRole('button', { name: 'Tous' })).toHaveAttribute('aria-pressed', 'false');
    });

    it('filtre par note minimale via les pastilles', () => {
      renderAt('/recherche');

      fireEvent.click(screen.getByRole('button', { name: /4,5 et plus/ }));

      expect(lastFilters()).toEqual({ minRating: 4.5 });
    });

    it('n’interroge le serveur qu’après une pause de saisie (debounce)', () => {
      vi.useFakeTimers();
      renderAt('/recherche');
      const callsBefore = mockedUseArtisans.mock.calls.length;

      fireEvent.change(screen.getByLabelText('Nom ou spécialité'), { target: { value: 'Diop' } });
      // Pendant la frappe : aucun nouveau filtre.
      expect(lastFilters()).toBeUndefined();

      act(() => {
        vi.advanceTimersByTime(400);
      });

      expect(mockedUseArtisans.mock.calls.length).toBeGreaterThan(callsBefore);
      expect(lastFilters()).toEqual({ search: 'Diop' });
    });

    it('réinitialise les filtres en conservant la position transmise par la demande IA', () => {
      mockedUseArtisans.mockReturnValue({
        data: [],
        isLoading: false,
        error: null,
        reload: vi.fn(),
      });
      renderAt('/recherche?trade=plomberie&note=4&q=x&lat=14.7&lng=-17.4');

      fireEvent.click(screen.getByRole('button', { name: 'Réinitialiser les filtres' }));

      expect(lastFilters()).toEqual({ near: { lat: 14.7, lng: -17.4 } });
    });
  });
});
