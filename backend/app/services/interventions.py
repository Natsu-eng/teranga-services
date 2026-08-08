"""Logique métier de `intervention` (BUILD_PLAN.md §2.2, §3.2, §6, §7 Lot 12).

Le cœur de l'entonnoir : la mise en relation entre un client et un artisan.
Fige le taux de commission en vigueur à l'instant de la création (résolu via
`app.services.commission`) -- ce taux ne bouge plus jamais pour cette
intervention, même si `commission_rate` change ensuite.

**Machine à états (BUILD_PLAN.md §6 Lot 12b)** -- `transition_intervention`
est l'unique porte d'entrée pour changer `intervention.status` : aucune
mutation directe (`intervention.status = ...`) ne doit exister ailleurs dans
le code, ici ou dans `app.services.quotes`/`app.services.reviews`.

```
proposee --(artisan accepte)--> acceptee --(devis accepté)--> en_cours --(complétion)--> terminee
proposee --(artisan refuse)--> annulee
```
Toute autre transition est rejetée (`TRANSITION_INTERVENTION_INVALIDE`).
`litige` n'a aucune transition entrante/sortante gérée dans ce lot.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.enums import ArtisanVerifiedStatus, InterventionStatus, Role, ServiceRequestStatus
from app.models.intervention import Intervention
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import interventions as interventions_repository
from app.repositories import requests as requests_repository
from app.repositories.requests import location_to_lat_lng
from app.schemas.interventions import InterventionCreateIn, InterventionOut
from app.schemas.pagination import Page
from app.schemas.quotes import QuoteOut
from app.schemas.reviews import ReviewOut
from app.services import commission as commission_service
from app.services import requests as requests_service
from app.services.artisans import PageHorsBornesError, get_artisan_or_404
from app.services.identity import public_display_name
from app.services.verification import compute_verified_status

# Transitions autorisées, par statut de départ (BUILD_PLAN.md §6 Lot 12b).
# Seule source de vérité : `transition_intervention` est le seul endroit qui
# doit lire cette table et le seul endroit autorisé à assigner
# `intervention.status`.
_ALLOWED_TRANSITIONS: dict[InterventionStatus, frozenset[InterventionStatus]] = {
    InterventionStatus.PROPOSEE: frozenset(
        {InterventionStatus.ACCEPTEE, InterventionStatus.ANNULEE}
    ),
    InterventionStatus.ACCEPTEE: frozenset({InterventionStatus.EN_COURS}),
    InterventionStatus.EN_COURS: frozenset({InterventionStatus.TERMINEE}),
    InterventionStatus.TERMINEE: frozenset(),
    InterventionStatus.ANNULEE: frozenset(),
    InterventionStatus.LITIGE: frozenset(),
}


class DemandeAutruiInterditeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_AUTRUI_INTERDITE",
            message="Cette demande n'appartient pas au client courant.",
            status_code=403,
        )


class DemandeNonOuverteError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DEMANDE_NON_OUVERTE",
            message="Cette demande n'est plus ouverte à une mise en relation.",
            status_code=409,
        )


class ArtisanNonVerifieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_NON_VERIFIE",
            message="Cet artisan n'est pas encore vérifié.",
            status_code=422,
        )


class ArtisanMetierNonExerceError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_METIER_NON_EXERCE",
            message="Cet artisan n'exerce pas le métier demandé.",
            status_code=422,
        )


class ArtisanHorsZoneError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ARTISAN_HORS_ZONE",
            message="Cet artisan ne couvre pas géographiquement cette demande.",
            status_code=422,
        )


class InterventionIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_NOT_FOUND", message="Intervention introuvable.", status_code=404
        )


class InterventionAccesInterditError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INTERVENTION_ACCES_INTERDIT",
            message="Vous n'avez pas accès à cette intervention.",
            status_code=403,
        )


class InterventionTransitionInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="TRANSITION_INTERVENTION_INVALIDE",
            message="Cette action n'est pas possible dans l'état actuel de l'intervention.",
            status_code=409,
        )


class ActionReserveeAutrePartieError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ACTION_RESERVEE_AUTRE_PARTIE",
            message="Cette action est réservée à l'autre partie de cette intervention.",
            status_code=403,
        )


def transition_intervention(intervention: Intervention, to: InterventionStatus) -> None:
    """Seule porte d'entrée pour changer `intervention.status` (BUILD_PLAN.md
    §6 Lot 12b) : centralise les transitions légales, jamais un
    `intervention.status = ...` dispersé ailleurs (ici ou dans
    `app.services.quotes`/`app.services.reviews`)."""
    allowed = _ALLOWED_TRANSITIONS.get(intervention.status, frozenset())
    if to not in allowed:
        raise InterventionTransitionInvalideError()
    intervention.status = to


def ensure_is_artisan(intervention: Intervention, user: User) -> None:
    """Lève si `user` n'est pas l'artisan de cette intervention -- garde des
    actions réservées à l'artisan (accepter/refuser la mise en relation,
    déposer un devis)."""
    if intervention.artisan.user_id != user.id:
        raise ActionReserveeAutrePartieError()


def ensure_is_client(intervention: Intervention, user: User) -> None:
    """Lève si `user` n'est pas le client de cette intervention -- garde des
    actions réservées au client (accepter/refuser un devis, confirmer la
    complétion, déposer un avis)."""
    if intervention.client_id != user.id:
        raise ActionReserveeAutrePartieError()


def to_intervention_out(intervention: Intervention) -> InterventionOut:
    """Assemble `InterventionOut` depuis une entité déjà chargée (avec
    `quote`/`review` eager-loadés) -- réutilisé par `app.services.quotes` et
    `app.services.reviews` pour refléter l'état de l'intervention après une
    de leurs actions."""
    return InterventionOut(
        id=intervention.id,
        service_request=requests_service.to_service_request_out(intervention.service_request),
        client_id=intervention.client_id,
        artisan_id=intervention.artisan_id,
        status=intervention.status,
        commission_rate_bps=intervention.commission_rate.rate_bps,
        agreed_amount_fcfa=intervention.agreed_amount_fcfa,
        scheduled_at=intervention.scheduled_at,
        completed_at=intervention.completed_at,
        decline_reason=intervention.decline_reason,
        quote=QuoteOut.model_validate(intervention.quote) if intervention.quote else None,
        review=(
            ReviewOut(
                id=intervention.review.id,
                rating=intervention.review.rating,
                comment=intervention.review.comment,
                author_name=public_display_name(intervention.review.author.full_name),
                created_at=intervention.review.created_at,
            )
            if intervention.review
            else None
        ),
        created_at=intervention.created_at,
    )


async def create_intervention(
    session: AsyncSession, *, client: User, payload: InterventionCreateIn, settings: Settings
) -> InterventionOut:
    """Crée la mise en relation (BUILD_PLAN.md §6 Lot 12). Ordre des règles :

    1. La demande existe, appartient au client courant, et est `ouverte`.
    2. L'artisan existe (compte actif, non supprimé).
    3. L'artisan est vérifié (`verified_status == VERIFIED`).
    4. L'artisan exerce le métier de la demande.
    5. La zone d'intervention de l'artisan (pour ce métier) couvre la
       position de la demande.
    6. Le taux de commission en vigueur pour ce métier est résolu et figé.

    La demande passe à `en_relation` -- elle ne peut plus recevoir d'autre
    intervention tant que celle-ci n'est pas close.
    """
    request = await requests_service.get_request_or_404(session, payload.service_request_id)
    if request.client_id != client.id:
        raise DemandeAutruiInterditeError()
    if request.status is not ServiceRequestStatus.OUVERTE:
        raise DemandeNonOuverteError()

    artisan = await get_artisan_or_404(session, payload.artisan_id)
    verified_status = compute_verified_status(
        artisan.verifications, settings.verification_required_doc_types
    )
    if verified_status is not ArtisanVerifiedStatus.VERIFIED:
        raise ArtisanNonVerifieError()

    exercises_trade = await artisans_repository.artisan_exercises_trade(
        session, artisan_id=artisan.id, trade_id=request.trade_id
    )
    if not exercises_trade:
        raise ArtisanMetierNonExerceError()

    lat, lng = location_to_lat_lng(request)
    reachable = await artisans_repository.is_artisan_reachable_for_trade(
        session, artisan_id=artisan.id, trade_id=request.trade_id, lat=lat, lng=lng
    )
    if not reachable:
        raise ArtisanHorsZoneError()

    rate = await commission_service.resolve_effective_commission_rate(
        session, trade_id=request.trade_id
    )

    intervention = await interventions_repository.create_intervention(
        session,
        service_request=request,
        client_id=client.id,
        artisan=artisan,
        commission_rate=rate,
    )
    await requests_repository.set_status(session, request, ServiceRequestStatus.EN_RELATION)

    return to_intervention_out(intervention)


async def get_intervention_or_404(
    session: AsyncSession, intervention_id: uuid.UUID
) -> Intervention:
    intervention = await interventions_repository.get_by_id(session, intervention_id)
    if intervention is None:
        raise InterventionIntrouvableError()
    return intervention


async def get_intervention_for_user(
    session: AsyncSession, *, intervention_id: uuid.UUID, user: User
) -> InterventionOut:
    intervention = await get_intervention_or_404(session, intervention_id)
    if intervention.client_id == user.id or intervention.artisan.user_id == user.id:
        return to_intervention_out(intervention)
    raise InterventionAccesInterditError()


async def list_my_interventions(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> Page[InterventionOut]:
    """S'adapte au rôle de l'utilisateur courant (BUILD_PLAN.md §6 Lot 12) :
    un client voit ses interventions comme client, un artisan les siennes
    comme artisan -- jamais les deux à la fois, jamais celles d'autrui."""
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved_page_size = min(page_size, settings.pagination_page_size_max)
    offset = (page - 1) * resolved_page_size

    if user.role is Role.ARTISAN:
        artisan_profile_id = await artisans_repository.get_artisan_profile_id_by_user_id(
            session, user.id
        )
        if artisan_profile_id is None:
            return Page.of([], page=page, page_size=resolved_page_size, total=0)
        interventions = await interventions_repository.list_for_artisan(
            session, artisan_profile_id, limit=resolved_page_size, offset=offset
        )
        total = await interventions_repository.count_for_artisan(session, artisan_profile_id)
    else:
        interventions = await interventions_repository.list_for_client(
            session, user.id, limit=resolved_page_size, offset=offset
        )
        total = await interventions_repository.count_for_client(session, user.id)

    items = [to_intervention_out(intervention) for intervention in interventions]
    return Page.of(items, page=page, page_size=resolved_page_size, total=total)


async def accept_intervention(
    session: AsyncSession, *, intervention_id: uuid.UUID, artisan_user: User
) -> InterventionOut:
    """L'artisan accepte la mise en relation (`proposee` -> `acceptee`,
    BUILD_PLAN.md §6 Lot 12b) : mesure le taux de réponse et ouvre le droit
    de deviser -- un artisan ne devise jamais sans avoir explicitement
    accepté au préalable."""
    intervention = await get_intervention_or_404(session, intervention_id)
    ensure_is_artisan(intervention, artisan_user)
    transition_intervention(intervention, InterventionStatus.ACCEPTEE)
    await session.flush()
    return to_intervention_out(intervention)


async def decline_intervention(
    session: AsyncSession, *, intervention_id: uuid.UUID, artisan_user: User, reason: str | None
) -> InterventionOut:
    """L'artisan refuse la mise en relation (`proposee` -> `annulee`,
    BUILD_PLAN.md §6 Lot 12b). La demande liée redevient `ouverte` : sans
    cette réouverture, elle resterait bloquée en `en_relation` (posé par
    `create_intervention`) sans qu'aucun endpoint ne permette de la proposer
    à un autre artisan -- le client doit pouvoir retenter une mise en
    relation ailleurs plutôt que rester coincé par un refus.
    """
    intervention = await get_intervention_or_404(session, intervention_id)
    ensure_is_artisan(intervention, artisan_user)
    transition_intervention(intervention, InterventionStatus.ANNULEE)
    intervention.decline_reason = reason
    await requests_repository.set_status(
        session, intervention.service_request, ServiceRequestStatus.OUVERTE
    )
    await session.flush()
    return to_intervention_out(intervention)


async def complete_intervention(
    session: AsyncSession, *, intervention_id: uuid.UUID, client_user: User
) -> InterventionOut:
    """Confirme la complétion (`en_cours` -> `terminee`, BUILD_PLAN.md §6 Lot 12b).

    **Qui déclenche : le client, seul.** Un unique acteur plutôt qu'un
    aller-retour "l'artisan signale terminé, le client confirme" (qui
    exigerait un statut intermédiaire absent du modèle de données actuel,
    BUILD_PLAN.md §2.2) -- mais délibérément le client, jamais l'artisan :
    laisser l'artisan clôturer unilatéralement ouvrirait la porte à une
    intervention marquée terminée (donc éligible à commission et à avis)
    sans que le client n'ait rien confirmé. Le client est la seule partie
    dont la confirmation ne crée aucun conflit d'intérêt vis-à-vis de la
    transition qu'elle déclenche.
    """
    intervention = await get_intervention_or_404(session, intervention_id)
    ensure_is_client(intervention, client_user)
    transition_intervention(intervention, InterventionStatus.TERMINEE)
    intervention.completed_at = datetime.now(UTC)
    await session.flush()
    return to_intervention_out(intervention)
