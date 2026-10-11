/**
 * Identité affichable d'un compte — ne montre JAMAIS un numéro de téléphone
 * comme s'il s'agissait d'un nom.
 *
 * Contexte : les comptes créés avant le correctif de confidentialité
 * (BUILD_PLAN.md, fix user-name-and-contact-privacy) ont parfois leur
 * numéro enregistré comme `full_name`. Le backend masque déjà ce cas dans
 * toutes les réponses PUBLIQUES (`app.services.identity`), mais renvoie la
 * valeur réelle en vue de soi (`/auth/me`) pour que l'utilisateur puisse la
 * corriger. Côté front, on évite donc de l'utiliser dans une salutation ou
 * des initiales, et on invite à renseigner un vrai nom.
 */

/** Séparateurs tolérés dans un numéro saisi à la main. */
const PHONE_SEPARATORS = /[\s.\-()]/g;

/** `+` optionnel puis 7 à 15 chiffres (longueurs possibles d'un numéro E.164 ou local). */
const PHONE_SHAPE = /^\+?\d{7,15}$/;

/**
 * La valeur ressemble-t-elle à un numéro de téléphone ? Heuristique
 * volontairement stricte : un nom réel contient des lettres et ne peut pas
 * correspondre (aucun faux positif sur un vrai nom).
 */
export function looksLikePhoneNumber(value: string): boolean {
  const compact = value.trim().replace(PHONE_SEPARATORS, '');
  return PHONE_SHAPE.test(compact);
}

/** Le compte a-t-il un vrai nom (ni vide, ni numéro de téléphone) ? */
export function hasRealName(fullName: string | null | undefined): boolean {
  return Boolean(fullName?.trim()) && !looksLikePhoneNumber(fullName ?? '');
}

/** Prénom pour une salutation (« Bonjour, Awa »), ou `null` sans vrai nom. */
export function firstNameOf(fullName: string | null | undefined): string | null {
  if (!hasRealName(fullName)) return null;
  return (fullName ?? '').trim().split(/\s+/)[0] ?? null;
}
