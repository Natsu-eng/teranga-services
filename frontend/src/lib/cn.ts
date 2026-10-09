/**
 * Assemble des classes CSS en ignorant les valeurs « vides » (false, null,
 * undefined, chaîne vide), pour écrire des classes conditionnelles lisibles :
 *   cn('base', isActive && 'actif', className)
 *
 * Volontairement sans fusion de classes Tailwind (tailwind-merge) : nos
 * tokens personnalisés (`text-display-lg` = taille, `text-primary` = couleur)
 * seraient pris pour des conflits sans configuration dédiée. Règle : les
 * variantes visuelles passent par les props des composants, `className` ne
 * sert qu'à la mise en page (marges, largeur, placement).
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ');
}
