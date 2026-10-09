/**
 * Base de toutes les URL d'API du front.
 *
 * - **Par défaut** : `/api/v1`, relatif à l'origine du front. En dev (et en
 *   `vite preview`), le proxy Vite le route vers FastAPI (vite.config.ts) ;
 *   en production, ce mode suppose un reverse proxy même-origine devant le
 *   front (aucune configuration CORS nécessaire).
 * - **`VITE_API_BASE_URL`** (lue au BUILD, jamais au runtime) : URL absolue
 *   du backend, ex. `https://api.teranga.sn/api/v1`, quand front et back sont
 *   servis sur deux origines distinctes (Vercel + Railway, BUILD_PLAN.md §1)
 *   -- l'origine du front doit alors figurer dans `CORS_ORIGINS` côté backend.
 *
 * Une valeur invalide fait échouer le chargement de l'application avec un
 * message explicite plutôt que de produire des appels réseau vers une URL
 * fantaisiste (erreurs opaques, ou pire : jeton d'accès envoyé ailleurs).
 */
export const DEFAULT_API_BASE_URL = '/api/v1';

export function resolveApiBaseUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim();
  if (value === '') return DEFAULT_API_BASE_URL;

  // Chemin relatif même-origine (ex. `/backend/api/v1` derrière un proxy).
  if (value.startsWith('/') && !value.startsWith('//')) {
    return value.replace(/\/+$/, '');
  }

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(
      `VITE_API_BASE_URL invalide : "${value}" (attendu : un chemin commençant par "/" ou une URL http(s) absolue).`,
    );
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    throw new Error(`VITE_API_BASE_URL doit utiliser https:// (ou http:// en local) : "${value}".`);
  }
  // Jamais d'identifiants ni de query/fragment dans une base d'API : ils
  // fuiteraient dans chaque requête (et dans les logs des proxys).
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error(`VITE_API_BASE_URL ne doit contenir ni identifiants, ni paramètres, ni fragment : "${value}".`);
  }
  return `${parsed.origin}${parsed.pathname.replace(/\/+$/, '')}`;
}
