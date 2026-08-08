"""Normalisation E.164 des numéros de téléphone (BUILD_PLAN.md §4.1).

Le téléphone est l'identifiant de connexion (`user.phone`) : sans
normalisation canonique appliquée avant toute écriture ou recherche,
plusieurs graphies du même numéro ("77 123 45 67", "0771234567",
"+221771234567"…) créeraient des comptes distincts. On s'appuie sur
`phonenumbers` (bibliothèque éprouvée, base de données Google des plans de
numérotation) plutôt que sur une regex maison.
"""

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

from app.core.config import Settings, get_settings
from app.core.errors import AppError


class PhoneInvalideError(AppError):
    def __init__(self, message: str = "Numéro de téléphone invalide.") -> None:
        super().__init__(code="TELEPHONE_INVALIDE", message=message, status_code=400)


def _try_parse(candidate: str, region: str) -> phonenumbers.PhoneNumber | None:
    try:
        parsed = phonenumbers.parse(candidate, region)
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return parsed


def normalize_phone(raw: str, settings: Settings | None = None) -> str:
    """Renvoie `raw` normalisé en E.164, ou lève `PhoneInvalideError`."""
    settings = settings or get_settings()
    candidate = raw.strip()
    if not candidate:
        raise PhoneInvalideError("Le numéro de téléphone est requis.")

    parsed = _try_parse(candidate, settings.phone_default_region)
    if parsed is None and not candidate.startswith("+") and candidate.startswith("0"):
        # Le plan de numérotation sénégalais n'utilise pas de préfixe de
        # tronc, mais certains numéros sont écrits par habitude avec un "0"
        # initial (convention française) -- on retente sans, une seule fois.
        parsed = _try_parse(candidate.removeprefix("0"), settings.phone_default_region)

    if parsed is None:
        raise PhoneInvalideError(f"« {raw} » n'est pas un numéro de téléphone valide.")

    region = phonenumbers.region_code_for_number(parsed)
    if region not in settings.phone_allowed_regions:
        raise PhoneInvalideError(
            f"Les numéros de téléphone de la région « {region} » ne sont pas encore pris en charge."
        )

    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def looks_like_phone_number(value: str, settings: Settings | None = None) -> bool:
    """`value` ressemble-t-il à un numéro de téléphone (E.164 ou variante
    locale) ? Utilisé pour ne jamais exposer publiquement un `full_name`
    resté au placeholder historique d'avant ce correctif (BUILD_PLAN.md,
    confidentialité du contact) -- `app.services.identity.public_display_name`.

    S'appuie sur `phonenumbers` plutôt qu'une regex maison : un nom légitime
    ne s'analyse (quasiment) jamais comme un numéro valide, donc le risque de
    faux positif (masquer un vrai nom) est négligeable face au risque de
    faux négatif (laisser fuiter un numéro) si on ratait un format local.
    """
    candidate = value.strip()
    if not candidate:
        return False
    settings = settings or get_settings()
    return _try_parse(candidate, settings.phone_default_region) is not None
