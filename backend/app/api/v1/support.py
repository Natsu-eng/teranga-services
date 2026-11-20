"""Aide : les demandes d'un client ou d'un artisan à Téranga (DEPLOYMENT.md §17).

Comptes connectés client ou artisan seulement ; chaque utilisateur ne lit
que SES demandes. L'admin les traite depuis `/api/v1/admin/support`.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.models.enums import Role
from app.models.user import User
from app.schemas.pagination import Page
from app.schemas.support import SupportTicketCreateIn, SupportTicketOut
from app.services import support as support_service
from app.services.admin_notifications import notify_support_ticket_created
from app.services.rate_limit import RateLimiter, get_support_ticket_rate_limiter

router = APIRouter(prefix="/support", tags=["support"])

Author = Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class TropDeDemandesAideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Vous avez envoyé plusieurs demandes d'aide récemment. Patientez un peu.",
            status_code=429,
        )


@router.post("/tickets", response_model=SupportTicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: SupportTicketCreateIn,
    session: SessionDep,
    settings: SettingsDep,
    user: Author,
    limiter: Annotated[RateLimiter, Depends(get_support_ticket_rate_limiter)],
    background_tasks: BackgroundTasks,
) -> SupportTicketOut:
    # Vérifié AVANT toute écriture : au-delà de la limite, rien n'est enregistré.
    if not await limiter.check(
        f"user:{user.id}",
        max_hits=settings.rate_limit_support_ticket_per_user_max,
        window_seconds=settings.rate_limit_support_ticket_per_user_window_seconds,
    ):
        raise TropDeDemandesAideError()
    created = await support_service.create_ticket(session, user=user, payload=payload)
    await session.commit()
    # Après le commit, en arrière-plan (best-effort) : un e-mail en échec ne
    # fait jamais échouer la demande.
    background_tasks.add_task(
        notify_support_ticket_created, created.category, created.author_role, settings
    )
    return created.ticket


@router.get("/tickets", response_model=Page[SupportTicketOut])
async def list_my_tickets(
    session: SessionDep,
    settings: SettingsDep,
    user: Author,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[SupportTicketOut]:
    """Les demandes de l'utilisateur connecté, et seulement les siennes."""
    return await support_service.list_my_tickets(
        session,
        user=user,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )
