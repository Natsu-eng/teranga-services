"""Endpoints /api/v1/artisans (BUILD_PLAN.md §3.2, §5, §6 Lot 9, onboarding
artisan).

Routes seules : extraction/validation superficielle des paramètres (types,
bornes triviales déléguées à FastAPI/Pydantic), toute la logique métier
(parsing de `near`, résolution du tri/rayon, plafond dur de pagination,
upload/stockage des documents) vit dans `app.services.artisans` et
`app.services.documents`.
"""

import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, require_role
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.models.enums import Role, VerificationDocType
from app.models.user import User
from app.repositories.artisans import ArtisanSort
from app.schemas.artisans import (
    ArtisanDetailOut,
    ArtisanListItemOut,
    ArtisanProfileUpdateIn,
    ArtisanStatsPrivateOut,
    ArtisanStatsPublicOut,
    ArtisanTradeCreateIn,
    MyVerificationOut,
    ProfileMediaConstraintsOut,
    VerificationDocumentOut,
)
from app.schemas.interventions import EngagementCheckOut
from app.schemas.pagination import Page
from app.schemas.reviews import ArtisanOwnReviewOut, ReviewOut, ReviewReportIn
from app.services import artisans as artisans_service
from app.services import avatars as avatars_service
from app.services import covers as covers_service
from app.services import documents as documents_service
from app.services import interventions as interventions_service
from app.services import reviews as reviews_service
from app.services.file_validation import MIME_BY_TYPE
from app.services.profile_media import discard_obsolete_media, media_constraints
from app.services.rate_limit import (
    RateLimiter,
    get_document_upload_rate_limiter,
    get_profile_media_upload_rate_limiter,
)
from app.services.storage import get_avatar_storage_backend, get_storage_backend

router = APIRouter(prefix="/artisans", tags=["artisans"])


class TropDeDemandesDocumentsError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Trop d'envois de documents, merci de réessayer plus tard.",
            status_code=429,
        )


class TropDeDemandesMediaError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TROP_DE_DEMANDES",
            message="Trop d'envois de photo, merci de réessayer plus tard.",
            status_code=429,
        )


@router.get("", response_model=Page[ArtisanListItemOut])
async def list_artisans(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    trade: Annotated[str | None, Query(description="Code du métier")] = None,
    near: Annotated[str | None, Query(description="Position du client, format lat,lng")] = None,
    radius_m: Annotated[
        int | None, Query(gt=0, description="Rayon de recherche, en mètres")
    ] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    available: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(description="Recherche libre sur le nom et la bio")] = None,
    sort: Annotated[ArtisanSort | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[ArtisanListItemOut]:
    return await artisans_service.list_artisans(
        session,
        trade=trade,
        near=near,
        radius_m=radius_m,
        min_rating=min_rating,
        available=available,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.patch("/me", response_model=ArtisanDetailOut)
async def update_my_profile(
    payload: ArtisanProfileUpdateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> ArtisanDetailOut:
    result = await artisans_service.update_profile(
        session, user=artisan, payload=payload, settings=settings
    )
    await session.commit()
    return result


async def _enforce_profile_media_budget(
    rate_limiter: RateLimiter, *, user: User, settings: Settings
) -> None:
    """Budget d'envois partagé entre l'avatar et la couverture (même
    limiteur, même clé `user:{id}` -- voir RATE_LIMIT_PROFILE_MEDIA_UPLOAD_*).
    Vérifié avant toute validation ou écriture : une fois la limite
    atteinte, un client qui insiste ne fait plus écrire le moindre fichier
    dans le stockage public."""
    allowed = await rate_limiter.check(
        f"user:{user.id}",
        max_hits=settings.rate_limit_profile_media_upload_per_user_max,
        window_seconds=settings.rate_limit_profile_media_upload_per_user_window_seconds,
    )
    if not allowed:
        raise TropDeDemandesMediaError()


@router.get("/me/media-constraints", response_model=ProfileMediaConstraintsOut)
async def get_my_media_constraints(
    settings: Annotated[Settings, Depends(get_settings)],
    _artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> ProfileMediaConstraintsOut:
    # Lu par l'onboarding avant tout envoi : le front n'a ainsi aucun
    # plafond recopié en dur, modifier AVATAR_/COVER_MAX_UPLOAD_BYTES suffit.
    return media_constraints(settings)


@router.post("/me/avatar", response_model=ArtisanDetailOut)
async def upload_my_avatar(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
    rate_limiter: Annotated[RateLimiter, Depends(get_profile_media_upload_rate_limiter)],
    file: Annotated[UploadFile, File()],
) -> ArtisanDetailOut:
    # Photo de profil : donnée PUBLIQUE, contrairement aux documents de
    # vérification -- stockage dédié (get_avatar_storage_backend), jamais
    # le stockage privé (get_storage_backend).
    await _enforce_profile_media_budget(rate_limiter, user=artisan, settings=settings)

    content = await file.read(settings.avatar_max_upload_bytes + 1)
    storage = get_avatar_storage_backend(settings)

    result = await avatars_service.upload_avatar(
        session,
        user=artisan,
        content=content,
        settings=settings,
        storage=storage,
    )
    await session.commit()
    # Seulement maintenant que la nouvelle URL est durablement enregistrée
    # (app/services/profile_media.py, règle 2).
    await discard_obsolete_media(storage, result.obsolete_key)
    return result.detail


@router.post("/me/cover", response_model=ArtisanDetailOut)
async def upload_my_cover(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
    rate_limiter: Annotated[RateLimiter, Depends(get_profile_media_upload_rate_limiter)],
    file: Annotated[UploadFile, File()],
) -> ArtisanDetailOut:
    # Photo de couverture : même régime PUBLIC que l'avatar ci-dessus, même
    # stockage, même budget d'envois.
    await _enforce_profile_media_budget(rate_limiter, user=artisan, settings=settings)

    content = await file.read(settings.cover_max_upload_bytes + 1)
    storage = get_avatar_storage_backend(settings)

    result = await covers_service.upload_cover(
        session,
        user=artisan,
        content=content,
        settings=settings,
        storage=storage,
    )
    await session.commit()
    await discard_obsolete_media(storage, result.obsolete_key)
    return result.detail


@router.post("/me/trades", response_model=ArtisanDetailOut, status_code=201)
async def add_my_trade(
    payload: ArtisanTradeCreateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> ArtisanDetailOut:
    result = await artisans_service.add_trade(
        session, user=artisan, payload=payload, settings=settings
    )
    await session.commit()
    return result


@router.delete("/me/trades/{artisan_trade_id}", response_model=ArtisanDetailOut)
async def remove_my_trade(
    artisan_trade_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> ArtisanDetailOut:
    result = await artisans_service.remove_trade(
        session, user=artisan, artisan_trade_id=artisan_trade_id, settings=settings
    )
    await session.commit()
    return result


@router.post("/me/documents", response_model=VerificationDocumentOut, status_code=201)
async def upload_my_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
    rate_limiter: Annotated[RateLimiter, Depends(get_document_upload_rate_limiter)],
    doc_type: Annotated[VerificationDocType, Form()],
    file: Annotated[UploadFile, File()],
) -> VerificationDocumentOut:
    allowed = await rate_limiter.check(
        f"user:{artisan.id}",
        max_hits=settings.rate_limit_document_upload_per_user_max,
        window_seconds=settings.rate_limit_document_upload_per_user_window_seconds,
    )
    if not allowed:
        raise TropDeDemandesDocumentsError()

    # Lu jusqu'à max+1 octets : suffit à détecter un dépassement de taille
    # sans buffériser en mémoire un fichier arbitrairement gros envoyé par
    # un client malveillant (app.services.documents rejette si > max).
    content = await file.read(settings.storage_max_upload_bytes + 1)

    result = await documents_service.upload_document(
        session,
        user=artisan,
        doc_type=doc_type,
        content=content,
        settings=settings,
        storage=get_storage_backend(settings),
    )
    await session.commit()
    return result


@router.get("/me/documents", response_model=MyVerificationOut)
async def list_my_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> MyVerificationOut:
    return await documents_service.list_my_documents(session, user=artisan, settings=settings)


@router.get("/me/documents/{document_id}/content")
async def get_my_document_content(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> StreamingResponse:
    content, detected = await documents_service.get_document_content(
        session,
        user=artisan,
        document_id=document_id,
        storage=get_storage_backend(settings),
    )
    return StreamingResponse(io.BytesIO(content), media_type=MIME_BY_TYPE[detected])


@router.get("/me/reviews", response_model=Page[ArtisanOwnReviewOut])
async def list_my_reviews(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[ArtisanOwnReviewOut]:
    """Tous les avis reçus, masqués compris, avec leur statut de modération."""
    return await reviews_service.list_own_reviews(
        session,
        user=artisan,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.post("/me/reviews/{review_id}/report", response_model=ArtisanOwnReviewOut)
async def report_my_review(
    review_id: uuid.UUID,
    payload: ReviewReportIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    artisan: Annotated[User, Depends(require_role(Role.ARTISAN))],
) -> ArtisanOwnReviewOut:
    """Signale un avis reçu (une fois, motif obligatoire). Il reste visible
    et compté jusqu'à la décision d'un admin."""
    result = await reviews_service.report_review(
        session, user=artisan, review_id=review_id, reason=payload.reason
    )
    await session.commit()
    return result


@router.get("/{artisan_id}", response_model=ArtisanDetailOut)
async def get_artisan(
    artisan_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    requester: Annotated[User | None, Depends(get_current_user_optional)],
) -> ArtisanDetailOut:
    return await artisans_service.get_artisan_detail(
        session, artisan_id, settings=settings, requester=requester
    )


@router.get("/{artisan_id}/coverage", response_model=EngagementCheckOut)
async def check_artisan_coverage(
    artisan_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    trade: Annotated[str, Query(min_length=1, description="Code du métier")],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
) -> EngagementCheckOut:
    """Cet artisan peut-il intervenir pour ce métier à ce lieu ? Même règle
    que `POST /interventions` (vérifié, métier exercé, zone d'intervention),
    en lecture seule : l'écran l'annonce avant que le client n'envoie quoi
    que ce soit. Public comme la fiche et la recherche par proximité, qui
    n'en révèlent pas moins."""
    return await interventions_service.check_coverage(
        session, artisan_id=artisan_id, trade_code=trade, lat=lat, lng=lng, settings=settings
    )


@router.get("/{artisan_id}/reviews", response_model=Page[ReviewOut])
async def list_artisan_reviews(
    artisan_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[ReviewOut]:
    return await reviews_service.list_artisan_reviews(
        session,
        artisan_id,
        page=page,
        page_size=page_size or settings.pagination_page_size_default,
        settings=settings,
    )


@router.get("/{artisan_id}/stats", response_model=None)
async def get_artisan_stats(
    artisan_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    requester: Annotated[User | None, Depends(get_current_user_optional)],
) -> ArtisanStatsPublicOut | ArtisanStatsPrivateOut:
    # response_model=None explicite : désactive la dérivation de FastAPI
    # depuis l'annotation de retour (union de deux schémas), qui réintroduit
    # sinon la même ambiguïté qu'un response_model=Union[...] explicite --
    # le retour Pydantic est alors sérialisé tel quel, avec exactement ses
    # propres champs, sans risque qu'un membre de l'union masque l'autre.
    return await artisans_service.get_stats(session, artisan_id=artisan_id, requester=requester)
