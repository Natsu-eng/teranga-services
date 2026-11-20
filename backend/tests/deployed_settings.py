"""Réglages qu'exige tout environnement DÉPLOYÉ (staging, production) depuis
le lot `feat/hardening-masking-otp` (app/core/config.py,
`validate_deployed_environment`).

Les tests qui construisent des réglages staging ou production les ajoutent :
la clé est GÉNÉRÉE à l'import (jamais une valeur écrite en dur), et une
valeur de `TRUSTED_PROXY_HOPS` réaliste est fournie.
"""

import secrets

# Même taille que scripts/generate_otp_hmac_key.py (256 bits, base64url).
TEST_OTP_HMAC_KEY = secrets.token_urlsafe(32)

DEPLOYED_REQUIRED: dict[str, object] = {
    "otp_hmac_key": TEST_OTP_HMAC_KEY,
    "trusted_proxy_hops": 1,
}
