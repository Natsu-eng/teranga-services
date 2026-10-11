import { useEffect, useState } from 'react';
import { api, ApiError } from '../../lib/api';
import type { Coordinates } from '../../lib/places';
import type { EngagementCheck } from '../../types';

interface CoverageResult {
  key: string;
  check: EngagementCheck | null;
  error: ApiError | null;
}

function coverageKey(artisanId: string, tradeCode: string, lat: number, lng: number): string {
  return `${artisanId}|${tradeCode}|${lat}|${lng}`;
}

/**
 * Cet artisan intervient-il pour ce métier à ce lieu ? Question posée au
 * SERVEUR (même règle que l'envoi), jamais devinée ici. `artisanId` ou
 * `tradeCode` nul : aucune requête.
 *
 * `isChecking` est dérivé (le résultat connu porte sur un autre lieu) :
 * aucun setState synchrone dans l'effet.
 */
export function useArtisanCoverage(
  artisanId: string | null,
  tradeCode: string | null,
  location: Coordinates,
) {
  const { lat, lng } = location;
  const key = artisanId && tradeCode ? coverageKey(artisanId, tradeCode, lat, lng) : '';
  const [result, setResult] = useState<CoverageResult | null>(null);

  useEffect(() => {
    if (!artisanId || !tradeCode) return;
    let ignore = false;
    const requestKey = coverageKey(artisanId, tradeCode, lat, lng);
    api
      .checkArtisanCoverage(artisanId, tradeCode, { lat, lng })
      .then((check) => {
        if (!ignore) setResult({ key: requestKey, check, error: null });
      })
      .catch((err: unknown) => {
        if (ignore) return;
        setResult({
          key: requestKey,
          check: null,
          error:
            err instanceof ApiError
              ? err
              : new ApiError('unknown', 'La zone de cet artisan n’a pas pu être vérifiée.'),
        });
      });
    return () => {
      ignore = true;
    };
  }, [artisanId, tradeCode, lat, lng]);

  const current = result && result.key === key ? result : null;
  return {
    check: current?.check ?? null,
    error: current?.error ?? null,
    isChecking: key !== '' && current === null,
  };
}
