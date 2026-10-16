"""Endpoints /api/v1/admin (BUILD_PLAN.md §3.6, back-office).

Toutes les routes exigent le rôle admin (`require_role(Role.ADMIN)`, même
dépendance que le reste de l'API, Lot 8), relu en base à chaque requête :
un retrait de rôle coupe l'accès immédiatement. Un client/artisan reçoit 403
ROLE_INSUFFISANT, un anonyme 401 NON_AUTHENTIFIE -- exactement les mêmes
erreurs génériques que n'importe quelle autre route protégée par rôle, sans
détail qui distinguerait une route admin d'une autre pour un tiers.

Le PREMIER admin naît uniquement du script `scripts/create_admin.py` ;
ensuite, un admin peut promouvoir/retirer d'autres comptes
(`/admin/users/...`), sous garde anti-verrouillage. Chaque action sensible
est inscrite au journal d'audit en ajout seul (`GET /admin/audit`).
"""

import io
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_payment_provider, require_role
from app.core.config import Settings, get_settings
from app.db.session import SessionFactory, get_session, get_session_factory
from app.models.enums import AuditAction, AuditTargetType, ReviewStatus, Role, VerificationStatus
from app.models.user import User
from app.schemas.admin import (
    AdminArtisanDetailOut,
    AdminArtisanListItemOut,
    AdminReviewOut,
    AdminRoleChangeIn,
    AdminUserOut,
    AdminVerificationListItemOut,
    ArtisanReactivateIn,
    ArtisanSuspendIn,
    ReviewHideIn,
    ReviewRestoreIn,
    VerificationRejectIn,
    VerificationReviewOut,
)
from app.schemas.admin_commission import (
    AdminCommissionRateOut,
    CommissionGridOut,
    CommissionRateCreateIn,
)
from app.schemas.admin_overview import AdminOverviewOut
from app.schemas.audit import AuditEntryOut
from app.schemas.interventions import InterventionOut
from app.schemas.pagination import Page
from app.schemas.payments import DisputeResolveIn
from app.services import admin_artisans as admin_artisans_service
from app.services import admin_commission as admin_commission_service
from app.services import admin_overview as admin_overview_service
from app.services import admin_reviews as admin_reviews_service
from app.services import admin_users as admin_users_service
from app.services import admin_verification as admin_verification_service
from app.services import audit as audit_service
from app.services import interventions as interventions_service
from app.services import payouts as payouts_service
from app.services.file_validation import MIME_BY_TYPE
from app.services.payment_providers.base import PaymentProvider
from app.services.storage import get_storage_backend

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/verifications", response_model=Page[AdminVerificationListItemOut])
async def list_verifications(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    status: Annotated[
        VerificationStatus | None, Query(description="Filtre par statut")
    ] = VerificationStatus.PENDING,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminVerificationListItemOut]:
    return await admin_verification_service.list_pending_verifications(
        session,
        status=status,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/verifications/{verification_id}/content")
async def get_verification_content(
    verification_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> StreamingResponse:
    content, detected = await admin_verification_service.get_verification_content(
        session, verification_id=verification_id, storage=get_storage_backend(settings)
    )
    return StreamingResponse(io.BytesIO(content), media_type=MIME_BY_TYPE[detected])


@router.post("/verifications/{verification_id}/approve", response_model=VerificationReviewOut)
async def approve_verification(
    verification_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> VerificationReviewOut:
    result = await admin_verification_service.approve_verification(
        session, admin=admin, verification_id=verification_id, settings=settings
    )
    await session.commit()
    return result


@router.post("/verifications/{verification_id}/reject", response_model=VerificationReviewOut)
async def reject_verification(
    verification_id: uuid.UUID,
    payload: VerificationRejectIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> VerificationReviewOut:
    result = await admin_verification_service.reject_verification(
        session,
        admin=admin,
        verification_id=verification_id,
        note=payload.note,
        settings=settings,
    )
    await session.commit()
    return result


@router.get("/artisans", response_model=Page[AdminArtisanListItemOut])
async def list_artisans(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    status: Annotated[
        Literal["none", "pending", "verified", "rejected", "suspended"] | None,
        Query(description="Statut de vérification, ou « suspended »"),
    ] = None,
    q: Annotated[str | None, Query(max_length=100, description="Nom ou téléphone")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminArtisanListItemOut]:
    """Tous les artisans, vérifiés ou non, suspendus compris."""
    return await admin_artisans_service.list_artisans(
        session,
        status=status,
        q=q,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/artisans/{artisan_id}/suspend", response_model=AdminArtisanDetailOut)
async def suspend_artisan(
    artisan_id: uuid.UUID,
    payload: ArtisanSuspendIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminArtisanDetailOut:
    """Suspend un artisan : invisible en recherche, inéligible aux NOUVELLES
    demandes ; ses interventions et paiements en cours continuent. Journalisé."""
    await admin_artisans_service.suspend_artisan(
        session, admin=admin, artisan_id=artisan_id, reason=payload.reason
    )
    await session.commit()
    return await admin_verification_service.get_artisan_detail_for_admin(
        session, artisan_id, settings=settings
    )


@router.post("/artisans/{artisan_id}/reactivate", response_model=AdminArtisanDetailOut)
async def reactivate_artisan(
    artisan_id: uuid.UUID,
    payload: ArtisanReactivateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminArtisanDetailOut:
    """Lève la suspension (motif facultatif). Journalisé."""
    await admin_artisans_service.reactivate_artisan(
        session, admin=admin, artisan_id=artisan_id, note=payload.note
    )
    await session.commit()
    return await admin_verification_service.get_artisan_detail_for_admin(
        session, artisan_id, settings=settings
    )


@router.get("/artisans/{artisan_id}", response_model=AdminArtisanDetailOut)
async def get_artisan(
    artisan_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminArtisanDetailOut:
    return await admin_verification_service.get_artisan_detail_for_admin(
        session, artisan_id, settings=settings
    )


@router.get("/disputes", response_model=Page[InterventionOut])
async def list_disputes(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    resolved: Annotated[bool, Query(description="Litiges déjà tranchés")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[InterventionOut]:
    """Litiges (BUILD_PLAN.md §3.5) : chaque intervention avec son volet
    financier complet (montant retenu, commission, versement) et le motif."""
    return await interventions_service.list_disputes(
        session,
        resolved=resolved,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/disputes/{intervention_id}/resolve", response_model=InterventionOut)
async def resolve_dispute(
    intervention_id: uuid.UUID,
    payload: DisputeResolveIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[PaymentProvider | None, Depends(get_payment_provider)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> InterventionOut:
    """Tranche un litige : `libere` (versement à l'artisan) ou `rembourse`
    (client remboursé). `admin` = celui authentifié, jamais un champ."""
    result = await interventions_service.resolve_dispute(
        session,
        intervention_id=intervention_id,
        admin=admin,
        outcome=payload.outcome,
        note=payload.note,
        settings=settings,
        provider=provider,
    )
    await session.commit()
    if result.payout_id is None:
        return result.intervention
    await payouts_service.dispatch_payout(
        session_factory, result.payout_id, provider=provider, settings=settings
    )
    return await interventions_service.get_intervention_for_admin(
        session, intervention_id=intervention_id
    )


@router.get("/audit", response_model=Page[AuditEntryOut])
async def list_audit_entries(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    action: Annotated[AuditAction | None, Query()] = None,
    target_type: Annotated[AuditTargetType | None, Query()] = None,
    target_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AuditEntryOut]:
    """Journal d'audit, du plus récent au plus ancien. LECTURE SEULE : aucune
    route ne modifie ni ne supprime une entrée (et la base le refuse)."""
    return await audit_service.list_entries(
        session,
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor_id=actor_id,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/overview", response_model=AdminOverviewOut)
async def get_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminOverviewOut:
    """Indicateurs du back-office, tous dérivés des tables métier (zéros
    honnêtes sans données, jamais de chiffre estimé)."""
    return await admin_overview_service.get_overview(session)


@router.get("/users", response_model=Page[AdminUserOut])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    q: Annotated[str | None, Query(max_length=100, description="Nom ou téléphone")] = None,
    role: Annotated[Role | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminUserOut]:
    return await admin_users_service.list_users(
        session,
        viewer=admin,
        q=q,
        role=role,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/users/{user_id}/grant-admin", response_model=AdminUserOut)
async def grant_admin(
    user_id: uuid.UUID,
    payload: AdminRoleChangeIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminUserOut:
    """Promeut un compte CLIENT dédié au rôle admin. Journalisé."""
    target = await admin_users_service.grant_admin(
        session, admin=admin, user_id=user_id, note=payload.note
    )
    await session.commit()
    return await admin_users_service.get_user(session, viewer=admin, user_id=target.id)


@router.post("/users/{user_id}/revoke-admin", response_model=AdminUserOut)
async def revoke_admin(
    user_id: uuid.UUID,
    payload: AdminRoleChangeIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminUserOut:
    """Retire le rôle admin (jamais le sien, jamais le dernier). Journalisé."""
    target = await admin_users_service.revoke_admin(
        session, admin=admin, user_id=user_id, note=payload.note
    )
    await session.commit()
    return await admin_users_service.get_user(session, viewer=admin, user_id=target.id)


@router.get("/reviews", response_model=Page[AdminReviewOut])
async def list_reviews(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    status: Annotated[ReviewStatus | None, Query()] = None,
    artisan_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Commentaire ou nom de l'auteur")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[AdminReviewOut]:
    """Avis à modérer : les signalés d'abord, sauf filtre de statut."""
    return await admin_reviews_service.list_reviews(
        session,
        status=status,
        artisan_id=artisan_id,
        q=q,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/reviews/{review_id}/hide", response_model=AdminReviewOut)
async def hide_review(
    review_id: uuid.UUID,
    payload: ReviewHideIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminReviewOut:
    """Masque un avis (motif obligatoire), recalcule la note. Journalisé, réversible."""
    result = await admin_reviews_service.hide_review(
        session, admin=admin, review_id=review_id, reason=payload.reason
    )
    await session.commit()
    return result


@router.post("/reviews/{review_id}/restore", response_model=AdminReviewOut)
async def restore_review(
    review_id: uuid.UUID,
    payload: ReviewRestoreIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminReviewOut:
    """Rétablit un avis masqué, ou maintient un avis signalé. Recalcule la
    note. Journalisé."""
    result = await admin_reviews_service.restore_review(
        session, admin=admin, review_id=review_id, note=payload.note
    )
    await session.commit()
    return result


@router.get("/commission-rates", response_model=CommissionGridOut)
async def get_commission_grid(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
    trade_code: Annotated[str | None, Query(max_length=50)] = None,
) -> CommissionGridOut:
    """Toute la grille : en vigueur, programmés, archivés, avec le nombre
    d'interventions qui ont figé chaque taux."""
    return await admin_commission_service.get_grid(
        session, trade_code=trade_code, settings=settings
    )


@router.post("/commission-rates", response_model=AdminCommissionRateOut, status_code=201)
async def add_commission_rate(
    payload: CommissionRateCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> AdminCommissionRateOut:
    """AJOUTE un taux daté (jamais d'édition ni de suppression) ; le taux de
    même portée en vigueur se termine où il commence. Les interventions
    existantes gardent leur taux figé. Journalisé."""
    result = await admin_commission_service.create_rate(
        session,
        admin=admin,
        rate_bps=payload.rate_bps,
        trade_code=payload.trade_code,
        tier=payload.tier,
        effective_from=payload.effective_from,
        note=payload.note,
        settings=settings,
    )
    await session.commit()
    return result
