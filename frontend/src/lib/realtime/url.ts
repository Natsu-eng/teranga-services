/**
 * URL du canal temps réel, dérivée de la base d'API (base-url.ts) :
 * - base relative (`/api/v1`, même origine) -> `ws(s)://<hôte courant>/api/v1/realtime/ws`,
 *   `wss` dès que la page est servie en https ;
 * - base absolue (`https://api.exemple.sn/api/v1`) -> même hôte en `wss` (`ws` pour http).
 *
 * Aucun secret dans l'URL : le ticket voyage dans le sous-protocole.
 */
export function resolveRealtimeUrl(
  apiBase: string,
  location: Pick<Location, 'protocol' | 'host'>,
): string {
  const path = '/realtime/ws';
  if (apiBase.startsWith('/')) {
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${scheme}//${location.host}${apiBase}${path}`;
  }
  const url = new URL(apiBase);
  const scheme = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${url.host}${url.pathname.replace(/\/+$/, '')}${path}`;
}
