"""Grille de commission administrée (BUILD_PLAN.md §2.2, §3.6).

**Règles actées (non négociables) :**

- On AJOUTE un taux versionné ; on ne modifie ni ne supprime JAMAIS un taux.
  Une intervention fige à sa création le taux en vigueur
  (`intervention.commission_rate_id`) : ajouter un taux ne touche ni ses
  interventions ni leurs commissions.
- Date d'effet : maintenant par défaut, jamais dans le passé -- le passé
  comptable ne se réécrit pas.
- Le seul changement apporté à une ligne existante est la FIN de période
  (`effective_to`) du taux de même portée qui couvre la date d'effet : il
  se termine là où le nouveau commence. Sa période déjà écoulée -- celle
  qu'ont figée les interventions -- n'est jamais modifiée.
- Un taux programmé plus tard pour la même portée borne le nouveau taux
  (`effective_to` = son début) : la grille reste continue, sans trou ni
  chevauchement.
- La contrainte d'exclusion `commission_rate_no_time_overlap` reste le juge
  final : un conflit (même début, création concurrente) répond 409
  CHEVAUCHEMENT_TAUX, jamais l'erreur brute.
- Taux par palier d'abonnement : refusés (422) tant que le moteur ne les
  applique pas (`find_effective_rate` ne lit que `tier IS NULL`) -- on ne
  crée pas un réglage qui n'aurait aucun effet.
- Chaque ajout est journalisé (audit_log).
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.models.commission import CommissionRate
from app.models.enums import AuditAction, AuditTargetType, SubscriptionTier
from app.models.intervention import Intervention
from app.models.trade import Trade
from app.models.user import User
from app.schemas.admin_commission import AdminCommissionRateOut, CommissionGridOut
from app.services import audit as audit_service

RateState = Literal["en_vigueur", "programme", "archive"]


class PalierNonAppliqueError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PALIER_NON_APPLIQUE",
            message=(
                "Les taux par palier d'abonnement ne sont pas encore appliqués au calcul "
                "des commissions : un tel taux n'aurait aucun effet."
            ),
            status_code=422,
        )


class DateEffetPasseeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="DATE_EFFET_PASSEE",
            message=(
                "La date d'effet ne peut pas être dans le passé : les commissions passées "
                "restent calculées sur le taux qu'elles ont figé."
            ),
            status_code=422,
        )


class TauxTropEleveError(AppError):
    def __init__(self, max_bps: int) -> None:
        super().__init__(
            code="TAUX_TROP_ELEVE",
            message=f"Le taux ne peut pas dépasser {max_bps / 100:g} %.",
            status_code=422,
        )


class MetierIntrouvableError(AppError):
    def __init__(self) -> None:
        super().__init__(code="TRADE_NOT_FOUND", message="Métier introuvable.", status_code=404)


class ChevauchementTauxError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(code="CHEVAUCHEMENT_TAUX", message=detail, status_code=409)


def _state(rate: CommissionRate, now: datetime) -> RateState:
    if rate.effective_from > now:
        return "programme"
    if rate.effective_to is not None and rate.effective_to <= now:
        return "archive"
    return "en_vigueur"


def _to_out(rate: CommissionRate, *, interventions: int, now: datetime) -> AdminCommissionRateOut:
    return AdminCommissionRateOut(
        id=rate.id,
        rate_bps=rate.rate_bps,
        trade_id=rate.trade_id,
        trade_code=rate.trade.code if rate.trade is not None else None,
        trade_label=rate.trade.label_fr if rate.trade is not None else None,
        tier=rate.tier,
        effective_from=rate.effective_from,
        effective_to=rate.effective_to,
        state=_state(rate, now),
        interventions_count=interventions,
        created_at=rate.created_at,
    )


async def _interventions_by_rate(
    session: AsyncSession, rate_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not rate_ids:
        return {}
    rows = await session.execute(
        select(Intervention.commission_rate_id, func.count())
        .where(Intervention.commission_rate_id.in_(rate_ids))
        .group_by(Intervention.commission_rate_id)
    )
    return {rate_id: int(total) for rate_id, total in rows.all()}


async def get_grid(
    session: AsyncSession, *, trade_code: str | None, settings: Settings
) -> CommissionGridOut:
    """Toute la grille (ou celle d'un métier), sans pagination : c'est une
    table de configuration à faible volume, qui ne grossit que par ajouts
    d'admin -- la tronquer cacherait un taux en silence. Taux global d'abord,
    puis par métier, le plus récent en tête."""
    conditions: list[ColumnElement[bool]] = []
    if trade_code is not None:
        trade = await _trade_by_code(session, trade_code)
        conditions.append(CommissionRate.trade_id == trade.id)
    rates = list(
        (
            await session.execute(
                select(CommissionRate)
                .outerjoin(Trade, Trade.id == CommissionRate.trade_id)
                .where(*conditions)
                .options(joinedload(CommissionRate.trade))
                .order_by(
                    CommissionRate.trade_id.is_not(None),
                    Trade.label_fr,
                    CommissionRate.effective_from.desc(),
                )
            )
        ).scalars()
    )
    counts = await _interventions_by_rate(session, [rate.id for rate in rates])
    now = datetime.now(UTC)
    return CommissionGridOut(
        items=[_to_out(rate, interventions=counts.get(rate.id, 0), now=now) for rate in rates],
        max_rate_bps=settings.commission_rate_max_bps,
        generated_at=now,
    )


async def _trade_by_code(session: AsyncSession, code: str) -> Trade:
    trade = (await session.execute(select(Trade).where(Trade.code == code))).scalar_one_or_none()
    if trade is None:
        raise MetierIntrouvableError()
    return trade


async def _lock_scope(session: AsyncSession, trade_id: uuid.UUID | None) -> list[CommissionRate]:
    """Toutes les lignes de même portée, verrouillées : deux ajouts simultanés
    sur la même portée sont sérialisés. La contrainte d'exclusion reste le
    filet final, notamment pour une portée encore vide (rien à verrouiller)."""
    stmt = (
        select(CommissionRate)
        .where(
            CommissionRate.trade_id.is_not_distinct_from(trade_id),
            CommissionRate.tier.is_(None),
        )
        .order_by(CommissionRate.effective_from)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(stmt)).scalars())


async def create_rate(
    session: AsyncSession,
    *,
    admin: User,
    rate_bps: int,
    trade_code: str | None,
    tier: SubscriptionTier | None,
    effective_from: datetime | None,
    note: str | None,
    settings: Settings,
) -> AdminCommissionRateOut:
    if tier is not None:
        raise PalierNonAppliqueError()
    if rate_bps > settings.commission_rate_max_bps:
        raise TauxTropEleveError(settings.commission_rate_max_bps)
    now = datetime.now(UTC)
    start = effective_from or now
    if start < now:
        raise DateEffetPasseeError()
    trade = await _trade_by_code(session, trade_code) if trade_code is not None else None
    trade_id = trade.id if trade is not None else None

    scope = await _lock_scope(session, trade_id)
    current: CommissionRate | None = None
    next_start: datetime | None = None
    for rate in scope:
        if rate.effective_from == start:
            raise ChevauchementTauxError(
                "Un taux de même portée commence déjà à cette date : choisissez une autre "
                "date d'effet."
            )
        if rate.effective_from < start and (rate.effective_to is None or rate.effective_to > start):
            current = rate
        elif rate.effective_from > start and next_start is None:
            next_start = rate.effective_from

    closed: dict[str, object] | None = None
    if current is not None:
        closed = {"id": current.id, "previous_effective_to": current.effective_to}
        # Fin de période uniquement, et toujours dans le futur (start >= now) :
        # la période écoulée, figée par les interventions, reste intacte.
        current.effective_to = start

    created = CommissionRate(
        rate_bps=rate_bps,
        trade_id=trade_id,
        tier=None,
        effective_from=start,
        effective_to=next_start,
    )
    try:
        async with session.begin_nested():
            # Clôture écrite AVANT l'insertion : la contrainte d'exclusion,
            # immédiate, verrait sinon deux périodes qui se chevauchent.
            await session.flush()
            session.add(created)
            await session.flush()
    except IntegrityError as exc:
        raise ChevauchementTauxError(
            "Ce taux chevaucherait un taux existant de même portée (ajout simultané ?) : "
            "rechargez la grille et réessayez."
        ) from exc

    await audit_service.record(
        session,
        actor=admin,
        action=AuditAction.COMMISSION_RATE_CREATE,
        target_type=AuditTargetType.COMMISSION_RATE,
        target_id=created.id,
        details={
            "rate_bps": rate_bps,
            "trade_code": trade_code,
            "effective_from": start,
            "effective_to": next_start,
            "closed_rate": closed,
            "note": note,
        },
    )
    created.trade = trade
    return _to_out(created, interventions=0, now=now)
