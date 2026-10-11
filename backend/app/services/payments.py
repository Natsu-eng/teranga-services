"""Moteur de paiement : séquestre, espèces, commission, versement
(BUILD_PLAN.md §3.5).

**Principes**

- Le montant vient TOUJOURS du serveur : `intervention.agreed_amount_fcfa`,
  posé à l'acceptation du devis. Aucune route ne reçoit de montant.
- La commission se calcule TOUJOURS sur le taux FIGÉ de l'intervention
  (`intervention.commission_rate`, résolu à sa création), jamais sur le taux
  courant, en entiers (`app.services.commission_calculation`).
- **En ligne = séquestre** : le client paie à l'acceptation du devis, les
  fonds sont RETENUS par Téranga (`retenu`) ; à la complétion confirmée par
  le client, ils sont libérés (`libere`) et l'artisan reçoit montant -
  commission ; annulation avant complétion -> remboursement (`rembourse`),
  ni versement ni commission.
- **Espèces** : réglées directement à l'artisan (`reussi`), pas de
  séquestre ni de versement ; la commission reste `due` par l'artisan
  (mesure de la fuite, recouvrement hors périmètre du code pour l'instant).
- **Concurrence** : toute décision financière sur une intervention se prend
  sous verrou de sa ligne (`SELECT ... FOR UPDATE`), webhook compris -- deux
  décisions ne s'entrecroisent jamais.
- **Fournisseur** : uniquement via le contrat `PaymentProvider` ; ce module
  ignore quel agrégateur est branché.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Mapping
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import SessionFactory
from app.models.enums import (
    InterventionStatus,
    PaymentChannel,
    PaymentStatus,
    PayoutStatus,
    PlatformFeeKind,
    PlatformFeeStatus,
    QuoteStatus,
    Role,
)
from app.models.intervention import Intervention
from app.models.payment import Payment, Payout, PlatformFee
from app.models.user import User
from app.repositories import artisans as artisans_repository
from app.repositories import interventions as interventions_repository
from app.repositories import payments as payments_repository
from app.schemas.pagination import Page
from app.schemas.payments import (
    ArtisanEarningsOut,
    ClientPaymentOut,
    EarningItemOut,
    EarningsTotalsOut,
    PaymentInitIn,
    PaymentOptionsOut,
    PaymentSummaryOut,
)
from app.services.artisans import PageHorsBornesError
from app.services.commission_calculation import compute_commission
from app.services.identity import public_display_name
from app.services.intervention_errors import (
    ActionReserveeAutrePartieError,
    InterventionAccesInterditError,
    InterventionIntrouvableError,
)
from app.services.payment_providers.base import (
    CheckoutRequest,
    InvalidWebhookSignatureError,
    MalformedWebhookError,
    PaymentProvider,
    PaymentProviderError,
    PayoutRequest,
    ProviderEvent,
    RefundRequest,
)
from app.services.payment_summary import commission_fee, current_payment, is_checkout_open
from app.services.payment_summary import summarize as summarize_payment

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ erreurs


class PaiementNonExigibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAIEMENT_NON_EXIGIBLE",
            message="Le paiement s'ouvre une fois le devis accepté, avant la fin des travaux.",
            status_code=409,
        )


class PaiementDejaEffectueError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAIEMENT_DEJA_EFFECTUE",
            message="Cette intervention est déjà réglée.",
            status_code=409,
        )


class MoyenPaiementIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="MOYEN_DE_PAIEMENT_INDISPONIBLE",
            message="Ce moyen de paiement n'est pas disponible pour le moment.",
            status_code=422,
        )


class FournisseurPaiementIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="FOURNISSEUR_PAIEMENT_INDISPONIBLE",
            message="Le service de paiement ne répond pas. Réessayez dans un instant.",
            status_code=502,
        )


class PaiementEnCoursError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAIEMENT_EN_COURS",
            message=(
                "Un paiement en ligne est en cours pour cette intervention : terminez-le "
                "ou attendez son expiration."
            ),
            status_code=409,
        )


class PaiementEnLigneDesactiveError(AppError):
    def __init__(self) -> None:
        super().__init__(code="NOT_FOUND", message="Ressource introuvable.", status_code=404)


class WebhookSignatureInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="WEBHOOK_SIGNATURE_INVALIDE",
            message="Notification non authentifiée.",
            status_code=401,
        )


class WebhookIllisibleError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="WEBHOOK_ILLISIBLE", message="Notification illisible.", status_code=400
        )


# ------------------------------------------------------------------ outils


async def _call_provider[T](awaitable: Awaitable[T], *, settings: Settings) -> T:
    """Appel au fournisseur borné dans le temps : un fournisseur lent ou
    injoignable donne une erreur propre, jamais une requête pendue."""
    try:
        async with asyncio.timeout(settings.payment_provider_timeout_seconds):
            return await awaitable
    except (PaymentProviderError, TimeoutError) as exc:
        logger.warning("Fournisseur de paiement indisponible : %s", exc)
        raise FournisseurPaiementIndisponibleError() from exc


def _now() -> datetime:
    return datetime.now(UTC)


async def _lock_intervention(session: AsyncSession, intervention_id: uuid.UUID) -> Intervention:
    intervention = await interventions_repository.get_by_id_for_update(session, intervention_id)
    if intervention is None:
        raise InterventionIntrouvableError()
    return intervention


def _ensure_client(intervention: Intervention, user: User) -> None:
    """Seul le client de l'intervention paie. L'artisan (autre partie) et un
    tiers reçoivent des refus distincts, comme partout ailleurs sur les
    interventions (BUILD_PLAN.md §6 Lot 12b)."""
    if intervention.client_id == user.id:
        return
    if intervention.artisan.user_id == user.id:
        raise ActionReserveeAutrePartieError()
    raise InterventionAccesInterditError()


def _provider_for(payment: Payment, provider: PaymentProvider | None) -> PaymentProvider:
    """Le fournisseur qui a porté ce paiement : un remboursement ne peut
    passer que par lui."""
    if provider is None or provider.name != payment.provider:
        logger.error(
            "Fournisseur %r requis pour le paiement %s, fournisseur actif : %r",
            payment.provider,
            payment.id,
            provider.name if provider is not None else None,
        )
        raise FournisseurPaiementIndisponibleError()
    return provider


def ensure_commission_fee(
    session: AsyncSession, intervention: Intervention, *, settings: Settings
) -> PlatformFee | None:
    """La commission de l'intervention (une seule), créée `due` au premier
    besoin, sur le taux FIGÉ de l'intervention. `None` si aucun montant
    n'est convenu (pas de devis accepté)."""
    existing = commission_fee(intervention)
    if existing is not None:
        return existing
    amount = intervention.agreed_amount_fcfa
    if amount is None:
        return None
    breakdown = compute_commission(
        amount, intervention.commission_rate.rate_bps, rounding=settings.commission_rounding
    )
    fee = PlatformFee(
        intervention=intervention,
        kind=PlatformFeeKind.COMMISSION,
        amount_fcfa=breakdown.commission_fcfa,
        commission_rate_id=intervention.commission_rate_id,
        status=PlatformFeeStatus.DUE,
    )
    session.add(fee)
    return fee


# ------------------------------------------------------------------ options


def get_options(settings: Settings, provider: PaymentProvider | None) -> PaymentOptionsOut:
    return PaymentOptionsOut(
        online_channels=list(settings.payment_online_channels) if provider is not None else [],
        cash_enabled=settings.payment_cash_enabled,
        currency=settings.payment_currency,
    )


# ------------------------------------------------------------------ initiation


async def init_payment(
    session: AsyncSession,
    *,
    user: User,
    payload: PaymentInitIn,
    settings: Settings,
    provider: PaymentProvider | None,
) -> PaymentSummaryOut:
    """Ouvre le paiement d'une intervention (client propriétaire seulement).

    - En ligne : paiement `en_attente` + page de paiement du fournisseur.
      Un double clic réutilise la page encore ouverte (même canal) au lieu
      d'en créer une seconde.
    - Espèces : paiement `reussi` enregistré, sans checkout.
    - Dans les deux cas, la commission est enregistrée (`due`) sur le taux
      figé de l'intervention.
    """
    intervention = await _lock_intervention(session, payload.intervention_id)
    _ensure_client(intervention, user)

    amount = intervention.agreed_amount_fcfa
    quote = intervention.quote
    if (
        intervention.status is not InterventionStatus.EN_COURS
        or amount is None
        or amount <= 0
        or quote is None
        or quote.status is not QuoteStatus.ACCEPTE
    ):
        raise PaiementNonExigibleError()

    is_cash = payload.channel is PaymentChannel.CASH
    if is_cash and not settings.payment_cash_enabled:
        raise MoyenPaiementIndisponibleError()
    if not is_cash and (
        provider is None or payload.channel not in settings.payment_online_channels
    ):
        raise MoyenPaiementIndisponibleError()

    now = _now()
    existing = current_payment(intervention)
    if existing is not None:
        if existing.status in (PaymentStatus.RETENU, PaymentStatus.LIBERE):
            raise PaiementDejaEffectueError()
        if existing.status is PaymentStatus.REUSSI:
            # Espèces déclarées : rien n'a transité par Téranga, le client
            # peut encore préférer payer en ligne (jamais l'inverse).
            if is_cash:
                raise PaiementDejaEffectueError()
            existing.status = PaymentStatus.ANNULE
        elif existing.status is PaymentStatus.EN_ATTENTE:
            if existing.channel is payload.channel and is_checkout_open(existing, now=now):
                # Idempotent : la page déjà ouverte reste la bonne.
                return _summary(intervention, settings)
            # Page expirée ou autre moyen choisi : l'ancienne est abandonnée.
            # Si elle était payée malgré tout, le webhook la remboursera.
            existing.status = (
                PaymentStatus.ANNULE
                if is_checkout_open(existing, now=now)
                else PaymentStatus.ECHOUE
            )
        # Libère la place du paiement vivant avant d'en créer un autre.
        await session.flush()

    ensure_commission_fee(session, intervention, settings=settings)

    if is_cash:
        session.add(
            Payment(
                intervention=intervention,
                amount_fcfa=amount,
                channel=PaymentChannel.CASH,
                status=PaymentStatus.REUSSI,
                paid_at=now,
                created_at=now,
            )
        )
        await session.flush()
        return _summary(intervention, settings)

    assert provider is not None  # garanti par la vérification du canal ci-dessus
    payment = Payment(
        intervention=intervention,
        amount_fcfa=amount,
        channel=payload.channel,
        status=PaymentStatus.EN_ATTENTE,
        provider=provider.name,
        created_at=now,
    )
    session.add(payment)
    await session.flush()

    front = settings.frontend_public_base_url.rstrip("/")
    checkout = await _call_provider(
        provider.create_checkout(
            CheckoutRequest(
                payment_id=str(payment.id),
                amount_fcfa=amount,
                currency=settings.payment_currency,
                channel=payload.channel,
                description=f"Téranga — {intervention.service_request.trade.label_fr}",
                # Pages de retour construites par le serveur : jamais une URL
                # fournie par le client (redirection ouverte).
                success_url=f"{front}/paiement/{intervention.id}?retour=succes",
                error_url=f"{front}/paiement/{intervention.id}?retour=echec",
                expires_at=now + timedelta(seconds=settings.payment_checkout_ttl_seconds),
            )
        ),
        settings=settings,
    )
    payment.provider_ref = checkout.provider_ref
    payment.checkout_url = checkout.checkout_url
    payment.checkout_expires_at = checkout.expires_at
    await session.flush()
    return _summary(intervention, settings)


def _summary(intervention: Intervention, settings: Settings) -> PaymentSummaryOut:
    summary = summarize_payment(intervention, rounding=settings.commission_rounding)
    assert summary is not None  # appelé seulement quand un montant est convenu
    return summary


# ------------------------------------------------------------------ webhook


async def _refund(
    payment: Payment, *, provider: PaymentProvider | None, settings: Settings
) -> None:
    """Rend au client les fonds d'un paiement reçu. Clé d'idempotence stable
    (`refund-<id>`) : si notre transaction échoue après l'appel, le rejouer
    ne rembourse pas deux fois."""
    assert payment.provider_ref is not None
    operation = await _call_provider(
        _provider_for(payment, provider).refund(
            RefundRequest(
                provider_ref=payment.provider_ref,
                amount_fcfa=payment.amount_fcfa,
                currency=settings.payment_currency,
                idempotency_key=f"refund-{payment.id}",
            )
        ),
        settings=settings,
    )
    payment.status = PaymentStatus.REMBOURSE
    payment.refunded_at = _now()
    payment.refund_ref = operation.reference


async def handle_webhook(
    session: AsyncSession,
    *,
    provider: PaymentProvider | None,
    payload: bytes,
    headers: Mapping[str, str],
    settings: Settings,
) -> str:
    """Traite une notification du fournisseur ; renvoie ce qui en a été fait.

    1. Signature vérifiée AVANT toute lecture (401 sinon, rien n'est écrit).
    2. Event id journalisé de façon atomique : déjà reçu -> `deja_traite`,
       aucun effet (le fournisseur retente jusqu'à 24 h).
    3. Paiement retrouvé par la référence du fournisseur, intervention
       verrouillée, puis transition :
       - succès d'un paiement `en_attente` -> `retenu` (séquestre) ;
       - succès d'un paiement abandonné (`annule`/`echoue`) -> remboursé
         aussitôt (paiement tardif, l'argent n'est jamais gardé sans cause) ;
       - montant ou devise incohérents -> aucune transition, anomalie
         journalisée pour traitement manuel ;
       - échec d'un paiement `en_attente` -> `echoue`.
    """
    if provider is None:
        raise PaiementEnLigneDesactiveError()
    try:
        provider.verify_webhook_signature(payload, headers)
    except InvalidWebhookSignatureError as exc:
        logger.warning("Webhook refusé : %s", exc)
        raise WebhookSignatureInvalideError() from exc
    try:
        event = provider.parse_event(payload)
    except MalformedWebhookError as exc:
        raise WebhookIllisibleError() from exc

    event_row_id = await payments_repository.record_event(
        session, provider=provider.name, event_id=event.event_id, event_type=event.raw_type
    )
    if event_row_id is None:
        logger.info("Webhook %s déjà traité : ignoré (idempotence).", event.event_id)
        return "deja_traite"

    outcome, payment_id = await _apply_event(
        session, provider=provider, event=event, settings=settings
    )
    await payments_repository.set_event_outcome(
        session, event_row_id=event_row_id, outcome=outcome, payment_id=payment_id
    )
    await session.flush()
    return outcome


async def _apply_event(
    session: AsyncSession,
    *,
    provider: PaymentProvider,
    event: ProviderEvent,
    settings: Settings,
) -> tuple[str, uuid.UUID | None]:
    if event.kind == "autre" or event.checkout_ref is None:
        return "ignore", None

    found = await payments_repository.find_payment_by_provider_ref(
        session, provider=provider.name, provider_ref=event.checkout_ref
    )
    if found is None:
        logger.warning("Webhook %s : paiement inconnu (%s).", event.event_id, event.checkout_ref)
        return "paiement_inconnu", None

    # Verrou de l'intervention, puis relecture du paiement sous ce verrou.
    intervention = await _lock_intervention(session, found.intervention_id)
    payment = next(p for p in intervention.payments if p.id == found.id)

    if event.kind == "checkout_echoue":
        if payment.status is PaymentStatus.EN_ATTENTE:
            payment.status = PaymentStatus.ECHOUE
            return "echoue", payment.id
        return "ignore", payment.id

    # checkout_reussi
    if event.amount_fcfa != payment.amount_fcfa or event.currency != settings.payment_currency:
        logger.error(
            "Webhook %s : montant/devise incohérents pour le paiement %s "
            "(reçu %s %s, attendu %s %s).",
            event.event_id,
            payment.id,
            event.amount_fcfa,
            event.currency,
            payment.amount_fcfa,
            settings.payment_currency,
        )
        return "montant_incoherent", payment.id
    if payment.status is PaymentStatus.EN_ATTENTE:
        payment.status = PaymentStatus.RETENU
        payment.paid_at = _now()
        return "retenu", payment.id
    if payment.status in (PaymentStatus.ANNULE, PaymentStatus.ECHOUE):
        await _refund(payment, provider=provider, settings=settings)
        logger.warning("Paiement tardif %s remboursé automatiquement.", payment.id)
        return "rembourse_paiement_tardif", payment.id
    # Déjà retenu, libéré ou remboursé : un second « succès » (autre event
    # id pour le même checkout) ne change rien.
    return "deja_traite", payment.id


# ------------------------------------------------------------------ complétion, annulation


def settle_on_completion(
    session: AsyncSession, intervention: Intervention, *, settings: Settings
) -> Payout | None:
    """À la complétion (intervention verrouillée par l'appelant) :

    - paiement en ligne `retenu` -> `libere`, commission `collectee`,
      versement du NET créé (`en_attente`, envoyé après le commit) ;
    - espèces : commission laissée `due` (due par l'artisan) ;
    - aucun paiement : commission `due` (travaux réglés hors plateforme --
      mesurés, jamais ignorés) ;
    - checkout encore ouvert -> refus (`PAIEMENT_EN_COURS`) : on ne clôt pas
      une intervention dont le paiement peut encore aboutir.
    """
    now = _now()
    payment = current_payment(intervention)
    if payment is not None and payment.status is PaymentStatus.EN_ATTENTE:
        if is_checkout_open(payment, now=now):
            raise PaiementEnCoursError()
        payment.status = PaymentStatus.ECHOUE

    fee = ensure_commission_fee(session, intervention, settings=settings)
    if payment is None or payment.status is not PaymentStatus.RETENU:
        return None

    assert fee is not None  # un paiement retenu implique un montant convenu
    payment.status = PaymentStatus.LIBERE
    payment.released_at = now
    fee.status = PlatformFeeStatus.COLLECTEE
    fee.settled_at = now
    artisan = intervention.artisan
    payout = Payout(
        artisan=artisan,
        intervention=intervention,
        amount_fcfa=payment.amount_fcfa - fee.amount_fcfa,
        channel=artisan.payout_channel or settings.payout_default_channel,
        status=PayoutStatus.EN_ATTENTE,
        # Toujours le numéro VÉRIFIÉ du compte artisan, jamais un autre.
        destination_phone=artisan.user.phone,
        provider=payment.provider or "",
        attempts=0,
    )
    session.add(payout)
    return payout


async def settle_on_cancellation(
    session: AsyncSession,
    intervention: Intervention,
    *,
    settings: Settings,
    provider: PaymentProvider | None,
) -> None:
    """À l'annulation (intervention verrouillée par l'appelant) : fonds
    retenus remboursés, checkout ouvert ou espèces déclarées annulés,
    commission annulée. Jamais de versement, jamais de commission."""
    payment = current_payment(intervention)
    if payment is not None:
        if payment.status is PaymentStatus.RETENU:
            await _refund(payment, provider=provider, settings=settings)
        elif payment.status in (PaymentStatus.EN_ATTENTE, PaymentStatus.REUSSI):
            payment.status = PaymentStatus.ANNULE
    fee = commission_fee(intervention)
    if fee is not None and fee.status is PlatformFeeStatus.DUE:
        fee.status = PlatformFeeStatus.ANNULEE
        fee.settled_at = _now()


def has_retained_funds(intervention: Intervention) -> bool:
    payment = current_payment(intervention)
    return payment is not None and payment.status is PaymentStatus.RETENU


# ------------------------------------------------------------------ versement


async def dispatch_payout(
    session_factory: SessionFactory,
    payout_id: uuid.UUID,
    *,
    provider: PaymentProvider | None,
    settings: Settings,
) -> PayoutStatus | None:
    """Envoie un versement, dans sa PROPRE transaction (après le commit de la
    complétion) : un fournisseur indisponible ne fait jamais échouer la
    confirmation du client. Ne lève jamais ; un échec laisse le versement
    `echoue`, relançable (`scripts/dispatch_payouts.py`). Clé d'idempotence
    `payout-<id>` : relancer ne verse jamais deux fois."""
    try:
        async with session_factory() as session:
            payout = await payments_repository.get_payout_for_update(session, payout_id)
            if payout is None or payout.status is PayoutStatus.ENVOYE:
                return payout.status if payout is not None else None
            payout.attempts += 1
            payout.last_attempt_at = _now()
            try:
                if provider is None or provider.name != payout.provider:
                    raise PaymentProviderError(
                        f"fournisseur {payout.provider!r} indisponible pour ce versement"
                    )
                async with asyncio.timeout(settings.payment_provider_timeout_seconds):
                    operation = await provider.send_payout(
                        PayoutRequest(
                            amount_fcfa=payout.amount_fcfa,
                            currency=settings.payment_currency,
                            channel=payout.channel,
                            destination_phone=payout.destination_phone,
                            idempotency_key=f"payout-{payout.id}",
                            description="Téranga — versement de votre intervention",
                        )
                    )
            except (PaymentProviderError, TimeoutError) as exc:
                payout.status = PayoutStatus.ECHOUE
                payout.failure_reason = str(exc) or exc.__class__.__name__
                logger.warning("Versement %s en échec : %s", payout.id, payout.failure_reason)
            else:
                payout.status = PayoutStatus.ENVOYE
                payout.provider_ref = operation.reference
                payout.sent_at = _now()
                payout.failure_reason = None
            status = payout.status
            await session.commit()
            return status
    except Exception:
        logger.exception("Versement %s : erreur inattendue, à relancer.", payout_id)
        return None


async def dispatch_pending_payouts(
    session_factory: SessionFactory,
    *,
    provider: PaymentProvider | None,
    settings: Settings,
    limit: int,
) -> dict[PayoutStatus | None, int]:
    """Relance les versements en attente ou en échec (script d'exploitation)."""
    async with session_factory() as session:
        payout_ids = await payments_repository.list_payout_ids_to_dispatch(session, limit=limit)
    results: dict[PayoutStatus | None, int] = {}
    for payout_id in payout_ids:
        status = await dispatch_payout(
            session_factory, payout_id, provider=provider, settings=settings
        )
        results[status] = results.get(status, 0) + 1
    return results


# ------------------------------------------------------------------ consultation


def _page_bounds(page: int, page_size: int, settings: Settings) -> tuple[int, int]:
    if page > settings.pagination_max_page:
        raise PageHorsBornesError()
    resolved = min(page_size, settings.pagination_page_size_max)
    return resolved, (page - 1) * resolved


async def list_client_payments(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> Page[ClientPaymentOut]:
    resolved, offset = _page_bounds(page, page_size, settings)
    payments = await payments_repository.list_payments_for_client(
        session, user.id, limit=resolved, offset=offset
    )
    total = await payments_repository.count_payments_for_client(session, user.id)
    items = [
        ClientPaymentOut(
            id=payment.id,
            intervention_id=payment.intervention_id,
            trade_label=payment.intervention.service_request.trade.label_fr,
            artisan_name=public_display_name(payment.intervention.artisan.user.full_name),
            amount_fcfa=payment.amount_fcfa,
            channel=payment.channel,
            status=payment.status,
            created_at=payment.created_at,
            paid_at=payment.paid_at,
            released_at=payment.released_at,
            refunded_at=payment.refunded_at,
        )
        for payment in payments
    ]
    return Page.of(items, page=page, page_size=resolved, total=total)


async def artisan_earnings(
    session: AsyncSession, *, user: User, page: int, page_size: int, settings: Settings
) -> ArtisanEarningsOut:
    """Gains de l'artisan courant : synthèse + détail par intervention, avec
    pour chacune le total, la commission prélevée et le net."""
    resolved, offset = _page_bounds(page, page_size, settings)
    artisan_id = await artisans_repository.get_artisan_profile_id_by_user_id(session, user.id)
    if artisan_id is None:
        return ArtisanEarningsOut(
            totals=EarningsTotalsOut(
                paid_out_fcfa=0,
                payout_pending_fcfa=0,
                in_escrow_fcfa=0,
                commission_collected_fcfa=0,
                cash_received_fcfa=0,
                commission_due_fcfa=0,
            ),
            items=[],
            pagination=Page.of([], page=page, page_size=resolved, total=0).pagination,
        )

    totals = await payments_repository.artisan_earnings_totals(session, artisan_id)
    ids = await payments_repository.list_paid_intervention_ids_for_artisan(
        session, artisan_id, limit=resolved, offset=offset
    )
    total = await payments_repository.count_paid_interventions_for_artisan(session, artisan_id)
    interventions = await interventions_repository.list_by_ids(session, ids)
    items = []
    for intervention in interventions:
        summary = summarize_payment(intervention, rounding=settings.commission_rounding)
        if summary is None:
            continue
        items.append(
            EarningItemOut(
                intervention_id=intervention.id,
                trade_label=intervention.service_request.trade.label_fr,
                client_name=public_display_name(intervention.client.full_name),
                intervention_status=intervention.status,
                payment=summary,
            )
        )
    return ArtisanEarningsOut(
        totals=EarningsTotalsOut(**totals),
        items=items,
        pagination=Page.of(items, page=page, page_size=resolved, total=total).pagination,
    )


def viewer_role(intervention: Intervention, user: User) -> Role | None:
    """Rôle de `user` dans cette intervention (`None` : tiers)."""
    if user.role is Role.ADMIN:
        return Role.ADMIN
    if intervention.client_id == user.id:
        return Role.CLIENT
    if intervention.artisan.user_id == user.id:
        return Role.ARTISAN
    return None
