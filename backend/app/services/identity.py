"""Nom public d'un utilisateur -- ne renvoie JAMAIS un numéro de téléphone
(fix confidentialité du contact, BUILD_PLAN.md). Filet de dernier recours
pour un compte créé avant ce correctif (le signup exige désormais un vrai
nom, `app.services.auth`) : sans ce filet, un compte legacy dont
`full_name` vaut encore le placeholder historique afficherait son numéro
partout où son nom apparaît publiquement (fiche artisan, avis...).

Utilisé par tout endroit qui expose un nom à un tiers non authentifié pour
ce compte -- `app.services.artisans` (fiche/recherche artisan),
`app.services.reviews` et `app.services.interventions` (auteur d'un avis,
visible par l'artisan concerné et en recherche publique). Jamais utilisé
pour le self-view (`/auth/me`, `UserOut`) : l'utilisateur voit toujours sa
propre valeur réelle, pour savoir qu'il doit la corriger.
"""

from app.core.phone import looks_like_phone_number

# Neutre, jamais spécifique à un rôle (utilisé aussi bien pour un artisan
# que pour l'auteur d'un avis, qui est un client) -- ne devrait plus jamais
# apparaître pour un compte créé après ce correctif.
PUBLIC_NAME_FALLBACK = "Membre Téranga"


def public_display_name(full_name: str) -> str:
    if looks_like_phone_number(full_name):
        return PUBLIC_NAME_FALLBACK
    return full_name
