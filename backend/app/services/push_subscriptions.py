"""Abonnements des appareils aux notifications push (Web Push).

- **Un abonnement par appareil**, plusieurs par compte (téléphone, ordinateur...),
  au plus WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER : au-delà, le plus ancien est
  oublié.
- **Enregistrement idempotent** : le front le renvoie à chaque ouverture de
  l'application (resynchronisation) ; un même navigateur passé à un autre
  compte est rattaché au nouveau (jamais de notification de l'ancien compte).
- **Contrôles avant tout enregistrement** : adresse https:// vers un service
  de push autorisé (protection SSRF, `is_allowed_push_endpoint`), clés du
  navigateur bien formées (point P-256 valide, secret de 16 octets).
- **Désabonnement** : seulement ses propres abonnements ; réponse identique
  qu'il existe ou non (aucune information sur les appareils d'autrui).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.vapid import b64url_decode, load_public_key
from app.models.user import User
from app.repositories import push_subscriptions as push_repository
from app.schemas.push import PushConfigOut, PushSubscriptionIn
from app.services.web_push import is_allowed_push_endpoint

# Secret d'authentification du navigateur (RFC 8291 §3.2) : 16 octets.
AUTH_SECRET_BYTES = 16


class NotificationsPushIndisponiblesError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="NOTIFICATIONS_PUSH_INDISPONIBLES",
            message="Les notifications ne sont pas disponibles pour le moment.",
            status_code=409,
        )


class AbonnementPushInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ABONNEMENT_PUSH_INVALIDE",
            message="Cet appareil ne peut pas recevoir les notifications de Téranga.",
            status_code=422,
        )


def push_config(settings: Settings) -> PushConfigOut:
    if not settings.web_push_enabled:
        return PushConfigOut(enabled=False, vapid_public_key=None)
    return PushConfigOut(enabled=True, vapid_public_key=settings.vapid_public_key)


def _keys_are_valid(p256dh: str, auth: str) -> bool:
    try:
        load_public_key(p256dh)
        return len(b64url_decode(auth)) == AUTH_SECRET_BYTES
    except ValueError:
        return False


async def subscribe(
    session: AsyncSession, *, user: User, payload: PushSubscriptionIn, settings: Settings
) -> None:
    if not settings.web_push_enabled:
        raise NotificationsPushIndisponiblesError()
    if not is_allowed_push_endpoint(payload.endpoint, settings.web_push_allowed_endpoint_hosts):
        raise AbonnementPushInvalideError()
    if not _keys_are_valid(payload.keys.p256dh, payload.keys.auth):
        raise AbonnementPushInvalideError()
    await push_repository.upsert(
        session,
        user_id=user.id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    await push_repository.keep_most_recent(
        session, user_id=user.id, keep=settings.web_push_max_subscriptions_per_user
    )


async def unsubscribe(session: AsyncSession, *, user: User, endpoint: str) -> None:
    """Toujours possible, même push désactivé (nettoyage à la déconnexion)."""
    await push_repository.delete_for_user(session, user_id=user.id, endpoint=endpoint)
