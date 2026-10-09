import { httpApiClient } from './http-impl';
import type { ApiClient } from './types';

export type { ApiClient, ApiErrorCode, ArtisanFilters } from './types';
export { ApiError } from './types';

// Point d'entrée unique de tout l'accès aux données : exclusivement le
// backend FastAPI. Plus aucun repli méthode par méthode sur `mockApiClient`
// (l'ancien `{ ...mockApiClient, ...httpApiClient }`, qui avait masqué de
// faux revenus artisan au Lot 12c) : `httpApiClient` implémente tout
// `ApiClient` (vérifié à la compilation) et le mock n'est plus importé par
// aucun code de production (règle ESLint `no-restricted-imports`,
// eslint.config.js) -- il n'existe donc même plus dans le bundle.
export const api: ApiClient = httpApiClient;
