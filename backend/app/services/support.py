"""Demandes d'aide (« Aide / Signaler un problème ») : un client ou un artisan
écrit à Téranga, un admin répond (BUILD_PLAN.md §3.6, DEPLOYMENT.md §17).

- **Ses propres demandes seulement** : la liste d'un utilisateur ne contient
  que celles dont il est l'auteur (filtre par `author_id`, jamais par un
  paramètre de la requête).
- **Intervention facultative, à l'auteur** : client ou artisan de cette
  intervention ; sinon la même erreur qu'une intervention inexistante (404,
  aucune fuite d'existence).
- **Message masqué** à l'écriture ET à la lecture (numéros, e-mails), comme
  les motifs de litige.
- **Réponse de l'admin** : sous verrou de la ligne, journalisée (journal
  d'audit en ajout seul, dans la même transaction) ; une demande résolue
  est définitive.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import (
    AuditAction,
    AuditTargetType,
    Role,
    SupportCategory,
    SupportTicketStatus,
)
from app.models.support import SupportTicket
from app.models.user import User
from app.repositories import interventions as interventions_repository
from app.repositories import support_tickets as support_repository
from app.schemas.pagination import Page
from app.schemas.support import AdminSupportTicketOut, SupportTicketCreateIn, SupportTicketOut
from app.services import audit as audit_service
from app.services.artisan_errors import PageHorsBornesError
from app.services.contact_masking import mask_contacts
from app.services.identity import public_display_name
from app.services.intervention_errors import InterventionIntrouvableError


class DemandeAideIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_AIDE_INTROUVABLE",
            message="Demande d'aide introuvable.",
            status_code=404,
        )


class DemandeAideDejaResolueError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_AIDE_DEJA_RESOLUE",
            message="Cette demande est déjà résolue : la réponse ne peut plus être modifiée.",
            status_code=409,
        )


@dataclass(frozen=True)
class CreatedTicket:
    """Demande enregistrée, et ce qu'il faut pour prévenir les admins (APRÈS
    le commit) : la catégorie et le rôle de l'auteur -- jamais le contenu."""

    ticket: SupportTicketOut
    category: SupportCategory
    author_role: Role


def _page_bounds(page: int, page_size: int, settings: Settings) -> tuple[int, int]:
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    size = min(page_size, settings.pagination_page_size_max)
    return size, (page - 1) * size


def _trade_label(ticket: SupportTicket) -> str | None:
    intervention = ticket.intervention
    return intervention.service_request.trade.label_fr if intervention is not None else None


def _to_out(ticket: SupportTicket) -> SupportTicketOut:
    return SupportTicketOut(
        id=ticket.id,
        category=ticket.category,
        # Masqué aussi à la LECTURE (idempotent) : jamais un numéro en clair.
        message=mask_contacts(ticket.message).text,
        intervention_id=ticket.intervention_id,
        intervention_trade_label=_trade_label(ticket),
        status=ticket.status,
        admin_reply=ticket.admin_reply,
        replied_at=ticket.replied_at,
        resolved_at=ticket.resolved_at,
        created_at=ticket.created_at,
    )


def _to_admin_out(ticket: SupportTicket) -> AdminSupportTicketOut:
    return AdminSupportTicketOut(
        **_to_out(ticket).model_dump(),
        author_id=ticket.author_id,
        author_name=public_display_name(ticket.author.full_name),
        author_role=ticket.author_role,
    )


async def _ensure_own_intervention(
    session: AsyncSession, *, intervention_id: uuid.UUID, user: User
) -> None:
    """L'intervention doit appartenir à l'auteur (client ou artisan) ; sinon
    404 identique à une intervention inexistante."""
    intervention = await interventions_repository.get_by_id(session, intervention_id)
    if intervention is None or user.id not in (
        intervention.client_id,
        intervention.artisan.user_id,
    ):
        raise InterventionIntrouvableError()


async def create_ticket(
    session: AsyncSession, *, user: User, payload: SupportTicketCreateIn
) -> CreatedTicket:
    if payload.intervention_id is not None:
        await _ensure_own_intervention(session, intervention_id=payload.intervention_id, user=user)
    ticket = SupportTicket(
        author_id=user.id,
        author_role=user.role,
        category=payload.category,
        # Masqué à l'écriture : la version d'origine n'est jamais conservée.
        message=mask_contacts(payload.message.strip()).text,
        intervention_id=payload.intervention_id,
        status=SupportTicketStatus.OUVERT,
    )
    session.add(ticket)
    await session.flush()
    stored = await support_repository.get_with_relations(session, ticket.id)
    assert stored is not None  # vient d'être enregistrée dans cette transaction
    return CreatedTicket(ticket=_to_out(stored), category=stored.category, author_role=user.role)


async def list_my_tickets(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> Page[SupportTicketOut]:
    size, offset = _page_bounds(page, page_size, settings)
    tickets = await support_repository.list_for_author(session, user.id, limit=size, offset=offset)
    total = await support_repository.count_for_author(session, user.id)
    return Page.of([_to_out(t) for t in tickets], page=page, page_size=size, total=total)


async def list_tickets_for_admin(
    session: AsyncSession,
    *,
    status: SupportTicketStatus,
    page: int,
    page_size: int,
    settings: Settings,
) -> Page[AdminSupportTicketOut]:
    size, offset = _page_bounds(page, page_size, settings)
    tickets = await support_repository.list_by_status(session, status, limit=size, offset=offset)
    total = await support_repository.count_by_status(session, status)
    return Page.of([_to_admin_out(t) for t in tickets], page=page, page_size=size, total=total)


async def reply_to_ticket(
    session: AsyncSession, *, admin: User, ticket_id: uuid.UUID, reply: str, resolve: bool
) -> AdminSupportTicketOut:
    """Réponse d'un admin, avec ou sans clôture. Journalisée dans la même
    transaction ; une demande résolue ne change plus."""
    ticket = await support_repository.get_for_update(session, ticket_id)
    if ticket is None:
        raise DemandeAideIntrouvableError()
    if ticket.status is SupportTicketStatus.RESOLU:
        raise DemandeAideDejaResolueError()
    now = datetime.now(UTC)
    ticket.admin_reply = reply.strip()
    ticket.replied_by_id = admin.id
    ticket.replied_at = now
    if resolve:
        ticket.status = SupportTicketStatus.RESOLU
        ticket.resolved_at = now
    await session.flush()
    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.SUPPORT_TICKET_REPLY,
        target_type=AuditTargetType.SUPPORT_TICKET,
        target_id=ticket.id,
        # Ni le message de l'utilisateur, ni son nom : la catégorie, la
        # réponse de l'admin (texte de Téranga) et l'issue suffisent.
        details={
            "category": ticket.category,
            "author_role": ticket.author_role,
            "reply": ticket.admin_reply,
            "resolved": resolve,
        },
    )
    return _to_admin_out(ticket)
