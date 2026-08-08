"""Validation du nom complet (`user.full_name`), partagée par l'inscription
(`app.services.auth`) et l'édition après coup (`app.services.users`,
`app.services.artisans`) -- une seule source de vérité pour les bornes.

Bornes volontairement simples et permissives (pas de regex sur les
caractères autorisés : les noms réels contiennent des espaces, apostrophes,
traits d'union, accents...) -- seule la longueur après nettoyage compte.
"""

from app.core.errors import AppError

# Aligné sur `user.full_name` (String(150), app/models/user.py) -- le
# maximum applicatif ne doit jamais dépasser la colonne DB.
FULL_NAME_MAX_LENGTH = 150
# 2 caractères : assez pour rejeter un caractère isolé ou une saisie vide
# après trim, sans être punitif pour un nom réel court.
FULL_NAME_MIN_LENGTH = 2


class NomInvalideError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="NOM_INVALIDE", message=message, status_code=422)


def validate_full_name(raw: str) -> str:
    """Renvoie `raw` nettoyé (trim), ou lève `NomInvalideError`."""
    candidate = raw.strip()
    if len(candidate) < FULL_NAME_MIN_LENGTH:
        raise NomInvalideError("Le nom est requis (au moins 2 caractères).")
    if len(candidate) > FULL_NAME_MAX_LENGTH:
        raise NomInvalideError(f"Le nom est trop long ({FULL_NAME_MAX_LENGTH} caractères maximum).")
    return candidate
