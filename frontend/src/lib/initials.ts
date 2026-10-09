/**
 * Initiales affichables d'un nom (2 lettres maximum, en capitales) :
 * « Awa Diop Ndiaye » -> « AD ». Chaîne vide si le nom est vide.
 * Source unique, partagée par l'Avatar, l'utilisateur courant et les avis.
 */
export function initialsFrom(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}
