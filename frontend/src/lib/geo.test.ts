import { afterEach, describe, expect, it, vi } from 'vitest';
import { GeolocationError, getCurrentPosition } from './geo';

function stubGeolocation(impl: Geolocation['getCurrentPosition'] | undefined) {
  vi.stubGlobal('navigator', {
    ...navigator,
    geolocation: impl ? { getCurrentPosition: impl } : undefined,
  });
}

describe('getCurrentPosition', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renvoie la position accordée par le navigateur', async () => {
    stubGeolocation((success) =>
      success({ coords: { latitude: 14.7, longitude: -17.45 } } as GeolocationPosition),
    );

    await expect(getCurrentPosition()).resolves.toEqual({ lat: 14.7, lng: -17.45 });
  });

  it.each([
    [1, 'denied'],
    [2, 'unavailable'],
    [3, 'timeout'],
  ] as const)(
    'rejette explicitement (code %s -> %s), sans position de repli silencieuse',
    async (code, reason) => {
      stubGeolocation((_success, failure) => failure?.({ code } as GeolocationPositionError));

      const result = getCurrentPosition();
      await expect(result).rejects.toBeInstanceOf(GeolocationError);
      await expect(result).rejects.toMatchObject({ reason });
    },
  );

  it('rejette sur un navigateur sans géolocalisation', async () => {
    stubGeolocation(undefined);

    await expect(getCurrentPosition()).rejects.toMatchObject({ reason: 'unsupported' });
  });
});
