/**
 * Quitte l'application vers une page externe (page de paiement hébergée
 * par le fournisseur). Isolé ici pour deux raisons :
 * - sécurité : seule une URL http(s) absolue est suivie — jamais un
 *   `javascript:` ou un schéma inattendu, même renvoyé par le serveur ;
 * - tests : jsdom n'implémente pas la navigation, ce module se remplace.
 */
export function isSafeExternalUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url);
    return protocol === 'https:' || protocol === 'http:';
  } catch {
    return false;
  }
}

export function navigateToExternal(url: string): void {
  if (!isSafeExternalUrl(url)) {
    throw new Error('URL de redirection refusée.');
  }
  window.location.assign(url);
}
