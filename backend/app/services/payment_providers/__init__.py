"""Choix du fournisseur de paiement actif -- POINT DE BASCULE UNIQUE
sandbox -> réel (BUILD_PLAN.md §3.5).

Le code métier reçoit un `PaymentProvider` et n'en connaît rien d'autre.
Brancher un agrégateur réel (PayDunya, CinetPay, Wave Business...) :

1. écrire son adaptateur (un module à côté de `sandbox.py`) qui implémente
   `PaymentProvider` -- traduction de son API et de ses webhooks vers les
   types neutres de `base.py` ;
2. l'ajouter ci-dessous et à `Settings.payment_provider` ;
3. renseigner `PAYMENT_PROVIDER`, `PAYMENT_WEBHOOK_SECRET` et ses
   identifiants ; déclarer chez lui l'URL `/api/v1/webhooks/payments`.

Aucune ligne de `app.services.payments` ne change.
"""

import hashlib
import hmac

from app.core.config import Settings
from app.services.payment_providers.base import PaymentProvider
from app.services.payment_providers.sandbox import SandboxProvider


def resolve_webhook_secret(settings: Settings) -> str:
    """Secret de signature des webhooks. En dev avec le sandbox, s'il n'est
    pas renseigné, il est DÉRIVÉ de JWT_SECRET (clé dédiée, jamais une valeur
    en dur) ; partout ailleurs la configuration l'exige (Settings)."""
    if settings.payment_webhook_secret:
        return settings.payment_webhook_secret
    return hmac.new(
        settings.jwt_secret.encode(), b"teranga-sandbox-webhook-secret", hashlib.sha256
    ).hexdigest()


def build_payment_provider(settings: Settings) -> PaymentProvider | None:
    """Le fournisseur configuré, ou `None` si le paiement en ligne est coupé
    (`PAYMENT_PROVIDER=disabled`)."""
    if settings.payment_provider == "sandbox":
        return SandboxProvider(
            webhook_secret=resolve_webhook_secret(settings),
            checkout_base_url=settings.backend_public_base_url,
            tolerance_seconds=settings.payment_webhook_tolerance_seconds,
        )
    return None
