"""Accès données de la messagerie (`conversation`, `message`).

Requêtes SQLAlchemy pures : jamais de Pydantic ici, jamais de logique métier
(autorisation, masquage, validation) -- voir `app.services.conversations`.

Performance : la liste des conversations ne fait jamais une requête par
ligne. Derniers messages et compteurs de non-lus sont calculés en une
requête groupée chacun, pour toute la page (pas de N+1).
"""

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.artisan import ArtisanProfile
from app.models.intervention import Intervention
from app.models.messaging import Conversation, Message
from app.models.request import ServiceRequest
from app.models.user import User


def _with_context(stmt: Select[tuple[Conversation]]) -> Select[tuple[Conversation]]:
    """Charge d'un coup tout ce qu'affichent la liste et l'en-tête d'un fil."""
    return stmt.options(
        joinedload(Conversation.intervention)
        .joinedload(Intervention.service_request)
        .joinedload(ServiceRequest.trade),
        joinedload(Conversation.client),
        joinedload(Conversation.artisan_user).joinedload(User.artisan_profile),
    )


def _participant_filter(user_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Conversation.client_id == user_id, Conversation.artisan_id == user_id)


async def create(
    session: AsyncSession,
    *,
    intervention: Intervention,
    client_id: uuid.UUID,
    artisan_user_id: uuid.UUID,
) -> Conversation:
    conversation = Conversation(
        intervention=intervention,
        service_request_id=intervention.service_request_id,
        client_id=client_id,
        artisan_id=artisan_user_id,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def get_by_id(session: AsyncSession, conversation_id: uuid.UUID) -> Conversation | None:
    stmt = _with_context(select(Conversation).where(Conversation.id == conversation_id))
    return (await session.execute(stmt)).unique().scalar_one_or_none()


async def get_by_intervention_id(
    session: AsyncSession, intervention_id: uuid.UUID
) -> Conversation | None:
    stmt = select(Conversation).where(Conversation.intervention_id == intervention_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _activity() -> ColumnElement[datetime]:
    return func.coalesce(Conversation.last_message_at, Conversation.created_at)


def _list_filters(
    user_id: uuid.UUID, artisan_profile_id: uuid.UUID | None
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [_participant_filter(user_id)]
    if artisan_profile_id is not None:
        # Fils du client avec un artisan précis (bouton « Message » de la fiche).
        filters.append(
            Conversation.artisan_id.in_(
                select(ArtisanProfile.user_id).where(ArtisanProfile.id == artisan_profile_id)
            )
        )
    return filters


async def list_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
    artisan_profile_id: uuid.UUID | None = None,
) -> list[Conversation]:
    stmt = _with_context(
        select(Conversation)
        .where(*_list_filters(user_id, artisan_profile_id))
        .order_by(_activity().desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).unique().scalars().all())


async def count_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, artisan_profile_id: uuid.UUID | None = None
) -> int:
    stmt = (
        select(func.count())
        .select_from(Conversation)
        .where(*_list_filters(user_id, artisan_profile_id))
    )
    return int((await session.execute(stmt)).scalar_one())


async def last_messages(
    session: AsyncSession, conversation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Message]:
    """Dernier message de chaque conversation (DISTINCT ON, une seule requête)."""
    if not conversation_ids:
        return {}
    stmt = (
        select(Message)
        .where(Message.conversation_id.in_(conversation_ids))
        .order_by(Message.conversation_id, Message.seq.desc())
        .distinct(Message.conversation_id)
    )
    return {message.conversation_id: message for message in (await session.execute(stmt)).scalars()}


def _unread_condition(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Message non lu par `user_id` : écrit par l'autre partie, et au-delà
    du curseur de lecture de `user_id` dans cette conversation."""
    my_cursor = case(
        (Conversation.client_id == user_id, Conversation.client_last_read_seq),
        else_=Conversation.artisan_last_read_seq,
    )
    return and_(Message.sender_id != user_id, Message.seq > my_cursor)


async def unread_counts(
    session: AsyncSession, *, conversation_ids: list[uuid.UUID], user_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    if not conversation_ids:
        return {}
    stmt = (
        select(Message.conversation_id, func.count())
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.conversation_id.in_(conversation_ids), _unread_condition(user_id))
        .group_by(Message.conversation_id)
    )
    return {conversation_id: int(count) for conversation_id, count in await session.execute(stmt)}


async def total_unread(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(_participant_filter(user_id), _unread_condition(user_id))
    )
    return int((await session.execute(stmt)).scalar_one())


async def list_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    limit: int,
    before_seq: int | None = None,
    since_seq: int | None = None,
) -> list[Message]:
    """Messages triés du plus ancien au plus récent.

    - `since_seq` : uniquement les messages postérieurs (nouveaux, repli
      polling) — les plus anciens d'abord, pour ne jamais en sauter un ;
    - sinon : les `limit` plus récents, éventuellement antérieurs à
      `before_seq` (remontée dans l'historique).
    """
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if since_seq is not None:
        stmt = stmt.where(Message.seq > since_seq).order_by(Message.seq.asc()).limit(limit)
        return list((await session.execute(stmt)).scalars().all())

    if before_seq is not None:
        stmt = stmt.where(Message.seq < before_seq)
    stmt = stmt.order_by(Message.seq.desc()).limit(limit)
    newest_first = list((await session.execute(stmt)).scalars().all())
    return list(reversed(newest_first))


async def has_messages_before(
    session: AsyncSession, *, conversation_id: uuid.UUID, seq: int
) -> bool:
    stmt = (
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.seq < seq)
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def get_message(
    session: AsyncSession, *, conversation_id: uuid.UUID, message_id: uuid.UUID
) -> Message | None:
    stmt = select(Message).where(
        Message.id == message_id, Message.conversation_id == conversation_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def add_message(
    session: AsyncSession,
    *,
    conversation: Conversation,
    sender_id: uuid.UUID,
    body: str,
    contact_masked: bool,
    attachment_key: str | None = None,
    attachment_content_type: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        sender_id=sender_id,
        body=body,
        contact_masked=contact_masked,
        attachment_key=attachment_key,
        attachment_content_type=attachment_content_type,
    )
    session.add(message)
    await session.flush()
    # `seq` (identité) et `created_at` (défaut serveur) sont posés par
    # Postgres : relus avant toute sérialisation.
    await session.refresh(message, attribute_names=["seq", "created_at"])
    # `clock_timestamp()` et non `now()` : `now()` est l'heure de DÉBUT de la
    # transaction, identique pour deux messages écrits dans la même
    # transaction -- l'ordre des conversations par activité deviendrait
    # arbitraire. `clock_timestamp()` est l'heure réelle de l'écriture.
    await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation.id)
        .values(last_message_at=func.clock_timestamp())
    )
    # L'auteur a forcément « vu » son propre message : son curseur avance.
    _advance_cursor(conversation, sender_id, message.seq)
    await session.flush()
    await session.refresh(conversation, attribute_names=["last_message_at"])
    return message


def _advance_cursor(conversation: Conversation, user_id: uuid.UUID, seq: int) -> None:
    if conversation.client_id == user_id:
        conversation.client_last_read_seq = max(conversation.client_last_read_seq, seq)
    elif conversation.artisan_id == user_id:
        conversation.artisan_last_read_seq = max(conversation.artisan_last_read_seq, seq)


async def mark_read(
    session: AsyncSession, *, conversation: Conversation, user_id: uuid.UUID, seq: int
) -> None:
    """Avance le curseur de lecture de `user_id` — jamais en arrière, et
    jamais au-delà du dernier message réellement présent dans le fil (un
    client ne peut pas « lire » un message qui n'existe pas encore).
    Mise à jour atomique (GREATEST côté SQL) : deux onglets qui marquent lu
    en même temps ne font jamais reculer le curseur."""
    max_seq_stmt = select(func.coalesce(func.max(Message.seq), 0)).where(
        Message.conversation_id == conversation.id
    )
    capped = func.least(seq, max_seq_stmt.scalar_subquery())
    column = (
        Conversation.client_last_read_seq
        if conversation.client_id == user_id
        else Conversation.artisan_last_read_seq
    )
    await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation.id)
        .values({column: func.greatest(column, capped)})
    )
    await session.refresh(
        conversation, attribute_names=["client_last_read_seq", "artisan_last_read_seq"]
    )


def last_activity(conversation: Conversation) -> datetime:
    return conversation.last_message_at or conversation.created_at
