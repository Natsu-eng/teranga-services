"""Mode OTP de TEST pour la beta (DEPLOYMENT.md, « Beta de test »).

En staging, des collaborateurs se connectent sans SMS payant : pour un
numéro de `OTP_TEST_WHITELIST`, le code émis est `OTP_TEST_CODE` et aucun
fournisseur SMS n'est appelé. RIEN d'autre ne change : le code est haché,
à usage unique, expirant, limité en tentatives et en débit, et la réponse
de `request-otp` reste identique pour tous les numéros (non-énumération).

**Impossible en production, par deux verrous INDÉPENDANTS :**

1. au démarrage, `Settings` refuse toute liste ou tout code de test hors de
   staging (production comprise, avec la liste de ses autres problèmes) ;
2. ici même, à l'exécution, le mode n'est actif que si
   `ENVIRONMENT == "staging"` : même une configuration qui aurait échappé
   à la validation (objet construit sans validation, valeur modifiée en
   cours de route) n'a aucun effet ailleurs qu'en staging.

Chaque verrou est prouvé par son propre test (tests/test_otp_test_mode.py).
"""

import secrets

from app.core.config import Settings


def staging_test_code_for(phone: str, settings: Settings) -> str | None:
    """Le code de test à émettre pour `phone` (E.164 normalisé), ou `None`
    pour le flux normal (code aléatoire envoyé par SMS)."""
    # Verrou n°2 : jamais hors de staging, quelle que soit la configuration.
    if settings.environment != "staging":
        return None
    code = settings.otp_test_code
    if not code or not settings.otp_test_whitelist:
        return None
    # Comparaison sans court-circuit sur le contenu : le temps de réponse ne
    # dépend pas de la position d'un numéro dans la liste.
    listed = False
    for number in settings.otp_test_whitelist:
        listed |= secrets.compare_digest(number.encode(), phone.encode())
    return code if listed else None


def is_test_mode_enabled(settings: Settings) -> bool:
    """Vrai si le mode OTP de test est actif (staging ET configuré). Sert à
    l'affichage (bandeau de test) : jamais la liste ni le code."""
    return (
        settings.environment == "staging"
        and bool(settings.otp_test_whitelist)
        and bool(settings.otp_test_code)
    )
