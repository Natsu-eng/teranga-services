"""Contraintes réelles du schéma de la messagerie (migration c0a26cec109e).

Exercées contre Postgres (pas de mock) : ce sont elles qui garantissent les
invariants même si un futur code applicatif se trompait.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_conversation, make_engagement, make_message


async def test_seq_is_strictly_increasing(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    first = await make_message(
        db_session, conversation=engagement.conversation, sender=engagement.client
    )
    second = await make_message(
        db_session, conversation=engagement.conversation, sender=engagement.artisan_user
    )

    assert second.seq > first.seq


async def test_new_conversation_starts_with_nothing_read(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)
    await db_session.refresh(engagement.conversation)

    assert engagement.conversation.client_last_read_seq == 0
    assert engagement.conversation.artisan_last_read_seq == 0
    assert engagement.conversation.last_message_at is None


async def test_message_without_text_nor_attachment_is_rejected(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    with pytest.raises(IntegrityError, match="ck_message_body_or_attachment"):
        await make_message(
            db_session, conversation=engagement.conversation, sender=engagement.client, body=""
        )


async def test_image_message_may_have_no_text(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    message = await make_message(
        db_session,
        conversation=engagement.conversation,
        sender=engagement.client,
        body="",
        attachment_key="conv/abc.jpg",
        attachment_content_type="image/jpeg",
    )

    assert message.attachment_key == "conv/abc.jpg"


async def test_attachment_reference_and_type_always_go_together(
    db_session: AsyncSession,
) -> None:
    engagement = await make_engagement(db_session)

    with pytest.raises(IntegrityError, match="ck_message_attachment_complete"):
        await make_message(
            db_session,
            conversation=engagement.conversation,
            sender=engagement.client,
            attachment_key="conv/abc.jpg",
            attachment_content_type=None,
        )


async def test_at_most_one_conversation_per_intervention(db_session: AsyncSession) -> None:
    engagement = await make_engagement(db_session)

    with pytest.raises(IntegrityError, match="uq_conversation_intervention_id"):
        await make_conversation(
            db_session,
            intervention=engagement.intervention,
            client=engagement.client,
            artisan_user=engagement.artisan_user,
        )
