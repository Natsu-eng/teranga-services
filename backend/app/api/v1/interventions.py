"""Endpoints /api/v1/interventions (BUILD_PLAN.md §3.2, §6 Lot 12).

Routes seules : toute la logique métier (règles d'engagement, résolution et
figeage du taux de commission, autorisation) vit dans
`app.services.interventions`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_payment_provider, require_role
from app.core.config import Settings, get_settings
from app.db.session import SessionFactory, get_session, get_session_factory
from app.models.enums import Role
from app.models.user import User
from app.schemas.interventions import InterventionCreateIn, InterventionDeclineIn, InterventionOut
from app.schemas.pagination import Page
from app.schemas.payments import DisputeOpenIn, InterventionCancelIn
from app.schemas.quotes import QuoteCreateIn
from app.schemas.reviews import ReviewCreateIn, ReviewOut
from app.services import interventions as interventions_service
from app.services import payments as payments_service
from app.services import quotes as quotes_service
from app.services import reviews as reviews_service
from app.services.payment_providers.base import PaymentProvider

router = APIRouter(prefix="/interventions", tags=["interventions"])

ProviderDep = Annotated[PaymentProvider | None, Depends(get_payment_provider)]


@router.post("", response_model=InterventionOut, status_code=status.HTTP_201_CREATED)
async def create_intervention(
    payload: InterventionCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> InterventionOut:
    result = await interventions_service.create_intervention(
        session, client=client, payload=payload, settings=settings
    )
    await session.commit()
    return result


@router.get("/me", response_model=Page[InterventionOut])
async def list_my_interventions(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[InterventionOut]:
    return await interventions_service.list_my_interventions(
        session,
        user=user,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/{intervention_id}", response_model=InterventionOut)
async def get_intervention(
    intervention_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> InterventionOut:
    return await interventions_service.get_intervention_for_user(
        session, intervention_id=intervention_id, user=user
    )


@router.post("/{intervention_id}/accept", response_model=InterventionOut)
async def accept_intervention(
    intervention_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> InterventionOut:
    result = await interventions_service.accept_intervention(
        session, intervention_id=intervention_id, artisan_user=artisan
    )
    await session.commit()
    return result


@router.post("/{intervention_id}/decline", response_model=InterventionOut)
async def decline_intervention(
    intervention_id: uuid.UUID,
    payload: InterventionDeclineIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> InterventionOut:
    result = await interventions_service.decline_intervention(
        session, intervention_id=intervention_id, artisan_user=artisan, reason=payload.reason
    )
    await session.commit()
    return result


@router.post("/{intervention_id}/complete", response_model=InterventionOut)
async def complete_intervention(
    intervention_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: ProviderDep,
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> InterventionOut:
    result = await interventions_service.complete_intervention(
        session, intervention_id=intervention_id, client_user=client, settings=settings
    )
    await session.commit()
    # Séquestre libéré et versement enregistrés : l'envoi au fournisseur se
    # fait APRÈS le commit, dans sa propre transaction -- un fournisseur
    # indisponible ne fait jamais échouer la confirmation du client.
    if result.payout_id is not None:
        await payments_service.dispatch_payout(
            session_factory, result.payout_id, provider=provider, settings=settings
        )
        # Relecture fraîche : le versement a été mis à jour par une autre
        # transaction.
        return await interventions_service.get_intervention_for_user(
            session, intervention_id=intervention_id, user=client, fresh=True
        )
    return result.intervention


@router.post("/{intervention_id}/cancel", response_model=InterventionOut)
async def cancel_intervention(
    intervention_id: uuid.UUID,
    payload: InterventionCancelIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: ProviderDep,
    user: Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))],
) -> InterventionOut:
    result = await interventions_service.cancel_intervention(
        session,
        intervention_id=intervention_id,
        user=user,
        reason=payload.reason,
        settings=settings,
        provider=provider,
    )
    await session.commit()
    return result


@router.post("/{intervention_id}/dispute", response_model=InterventionOut)
async def open_dispute(
    intervention_id: uuid.UUID,
    payload: DisputeOpenIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role(Role.CLIENT, Role.ARTISAN))],
) -> InterventionOut:
    result = await interventions_service.open_dispute(
        session, intervention_id=intervention_id, user=user, reason=payload.reason
    )
    await session.commit()
    return result


@router.post("/{intervention_id}/quote", response_model=InterventionOut)
async def create_quote(
    intervention_id: uuid.UUID,
    payload: QuoteCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> InterventionOut:
    result = await quotes_service.create_quote(
        session, intervention_id=intervention_id, artisan_user=artisan, payload=payload
    )
    await session.commit()
    return result


@router.post("/{intervention_id}/quote/accept", response_model=InterventionOut)
async def accept_quote(
    intervention_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> InterventionOut:
    result = await quotes_service.accept_quote(
        session, intervention_id=intervention_id, client_user=client
    )
    await session.commit()
    return result


@router.post("/{intervention_id}/quote/refuse", response_model=InterventionOut)
async def refuse_quote(
    intervention_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> InterventionOut:
    result = await quotes_service.refuse_quote(
        session, intervention_id=intervention_id, client_user=client
    )
    await session.commit()
    return result


@router.post(
    "/{intervention_id}/review", response_model=ReviewOut, status_code=status.HTTP_201_CREATED
)
async def create_review(
    intervention_id: uuid.UUID,
    payload: ReviewCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    client: Annotated[User, Depends(require_role(Role.CLIENT))],
) -> ReviewOut:
    result = await reviews_service.create_review(
        session, intervention_id=intervention_id, client_user=client, payload=payload
    )
    await session.commit()
    return result
