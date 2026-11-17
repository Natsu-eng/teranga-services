"""Schémas des notifications push (`/api/v1/push`).

Le corps d'abonnement reprend la forme de `PushSubscription.toJSON()` du
navigateur (`{endpoint, keys: {p256dh, auth}}`) ; `expirationTime` et tout
autre champ sont ignorés. Les bornes de longueur ne protègent que d'un corps
démesuré : le contenu est vérifié par le service (hôte autorisé, clés).
"""

from pydantic import BaseModel, Field

from app.models.push import (
    PUSH_AUTH_MAX_LENGTH,
    PUSH_ENDPOINT_MAX_LENGTH,
    PUSH_P256DH_MAX_LENGTH,
)


class PushConfigOut(BaseModel):
    """`enabled` faux : le front n'affiche aucune invitation."""

    enabled: bool
    # Clé publique VAPID (`applicationServerKey`), publique par nature.
    vapid_public_key: str | None


class PushKeysIn(BaseModel):
    p256dh: str = Field(min_length=1, max_length=PUSH_P256DH_MAX_LENGTH)
    auth: str = Field(min_length=1, max_length=PUSH_AUTH_MAX_LENGTH)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=PUSH_ENDPOINT_MAX_LENGTH)
    keys: PushKeysIn


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=PUSH_ENDPOINT_MAX_LENGTH)
