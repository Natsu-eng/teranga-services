"""Notification push « nouveau message » (messagerie in-app).

`notify_new_message` est appelée APRÈS l'enregistrement du message (tâche
d'arrière-plan de la route d'envoi), pour le SEUL destinataire -- jamais
l'expéditeur.

- **Pas de doublon à l'écran** : si le destinataire affiche déjà cette
  conversation (présence « fil ouvert », app/services/realtime.py), il voit
  le message arriver en temps réel : aucune notification.
- **Tous ses appareils** : un envoi par abonnement, en parallèle ; ceux que le
  service de push déclare morts (404/410) sont supprimés.
- **Contenu sobre, sans fuite** : « Nouveau message sur Téranga » et le lien
  du fil -- ni le texte du message, ni le nom, ni le numéro de quiconque.
  (Le contenu est en outre chiffré de bout en bout jusqu'à l'appareil.)
- **Best-effort, toujours** : ne lève jamais ; un échec est journalisé avec
  un détail sûr (statut HTTP, type d'erreur), jamais une adresse
  d'abonnement. L'envoi du message, déjà validé, n'en dépend pas.
"""

import asyncio
import logging
import uuid
from collections import Counter

from app.core.config import Settings
from app.db.session import SessionFactory
from app.repositories import push_subscriptions as push_repository
from app.services.realtime import ViewingPresence, viewing_presence
from app.services.web_push import (
    PushNotification,
    PushOutcome,
    PushResult,
    PushSender,
    PushTarget,
    WebPushSender,
)

logger = logging.getLogger(__name__)

NEW_MESSAGE_TITLE = "Téranga"
NEW_MESSAGE_BODY = "Nouveau message sur Téranga"


def build_new_message_notification(conversation_id: uuid.UUID) -> PushNotification:
    return PushNotification(
        title=NEW_MESSAGE_TITLE,
        body=NEW_MESSAGE_BODY,
        # Route du fil côté front (frontend/src/App.tsx, messages/:conversationId).
        url=f"/messages/{conversation_id}",
        tag=f"conversation-{conversation_id}",
        # 32 caractères hexadécimaux : dans la limite de l'en-tête Topic.
        topic=conversation_id.hex,
    )


async def _send_safely(
    sender: PushSender, target: PushTarget, notification: PushNotification
) -> PushResult:
    try:
        return await sender.send(target, notification)
    except Exception as exc:  # contrat : un envoi ne doit jamais lever
        return PushResult(PushOutcome.FAILED, type(exc).__name__)


async def notify_new_message(
    recipient_id: uuid.UUID,
    conversation_id: uuid.UUID,
    settings: Settings,
    session_factory: SessionFactory,
    *,
    sender: PushSender | None = None,
    presence: ViewingPresence | None = None,
) -> None:
    """Prévient `recipient_id` d'un nouveau message ; n'échoue JAMAIS."""
    if not settings.web_push_enabled:
        return
    try:
        if await (presence or viewing_presence()).is_viewing(recipient_id, conversation_id):
            logger.info("Nouveau message : fil déjà à l'écran du destinataire, aucun push.")
            return
        async with session_factory() as session:
            subscriptions = await push_repository.list_active_for_user(session, recipient_id)
            targets = [(s.id, PushTarget(s.endpoint, s.p256dh, s.auth)) for s in subscriptions]
        if not targets:
            return
        push_sender = sender or WebPushSender(settings)
        notification = build_new_message_notification(conversation_id)
        results = await asyncio.gather(
            *(_send_safely(push_sender, target, notification) for _, target in targets)
        )
        gone = [
            subscription_id
            for (subscription_id, _), result in zip(targets, results, strict=True)
            if result.outcome is PushOutcome.GONE
        ]
        if gone:
            async with session_factory() as session:
                await push_repository.delete_by_ids(session, gone)
                await session.commit()
        failures = Counter(r.detail for r in results if r.outcome is PushOutcome.FAILED)
        delivered = sum(r.outcome is PushOutcome.DELIVERED for r in results)
        logger.info(
            "Push nouveau message : %d appareil(s) notifié(s), %d abonnement(s) expiré(s) "
            "supprimé(s), %d échec(s)%s.",
            delivered,
            len(gone),
            sum(failures.values()),
            f" ({', '.join(f'{d} x{n}' for d, n in failures.items())})" if failures else "",
        )
    except Exception as exc:  # best-effort : rien ne doit remonter
        logger.error("Push nouveau message NON envoyé : %s.", type(exc).__name__)
