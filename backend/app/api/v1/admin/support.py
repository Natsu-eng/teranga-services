"""/api/v1/admin — Aide : file des demandes et réponses (journalisées).

Garde `require_role(Role.ADMIN)` sur chaque route (voir __init__.py).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import Role, SupportTicketStatus
from app.models.user import User
from app.schemas.pagination import Page
from app.schemas.support import AdminSupportTicketOut, SupportReplyIn
from app.services import support as support_service

router = APIRouter()


@router.get("/support/tickets", response_model=Page[AdminSupportTicketOut])
async def list_support_tickets(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    status: Annotated[SupportTicketStatus, Query()] = SupportTicketStatus.OUVERT,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminSupportTicketOut]:
    """Demandes ouvertes (la plus ancienne d'abord) ou résolues."""
    return await support_service.list_tickets_for_admin(
        session,
        status=status,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/support/tickets/{ticket_id}/reply", response_model=AdminSupportTicketOut)
async def reply_to_support_ticket(
    ticket_id: uuid.UUID,
    payload: SupportReplyIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminSupportTicketOut:
    """Répond à une demande, et la clôt si `resolve` (défaut). Journalisé.
    `admin` = celui authentifié, jamais un champ."""
    result = await support_service.reply_to_ticket(
        session, admin=admin, ticket_id=ticket_id, reply=payload.reply, resolve=payload.resolve
    )
    await session.commit()
    return result
