import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
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
    mockedUseTrades.mockReturnValue({ data: [], isLoading: false, error: null, reload: vi.fn() });
  });

  afterEach(cleanup);

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
});
