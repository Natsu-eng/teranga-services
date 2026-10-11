"""Page de paiement hébergée du fournisseur SANDBOX (BUILD_PLAN.md §3.5).

Joue le rôle de la page d'un agrégateur : affiche le montant (lu dans le
jeton signé, jamais modifiable), puis « paie » ou « échoue » et LIVRE la
notification signée au webhook `/api/v1/webhooks/payments` par HTTP, comme
le ferait le vrai fournisseur -- la vérification de signature et
l'idempotence sont donc exercées exactement comme en production. Le
navigateur est ensuite renvoyé vers la page de retour du front.

N'existe que si `PAYMENT_PROVIDER=sandbox` (404 sinon), lui-même interdit
en prod (Settings).
"""

import html
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.deps import get_payment_provider
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.payment_providers.base import InvalidWebhookSignatureError, PaymentProvider
from app.services.payment_providers.sandbox import (
    SIGNATURE_HEADER,
    SandboxOutcome,
    SandboxProvider,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

# (url, corps, en-têtes) -> code HTTP de la réponse du webhook.
WebhookDeliverer = Callable[[str, bytes, dict[str, str]], Awaitable[int]]

_CHANNEL_LABELS = {"wave": "Wave", "orange_money": "Orange Money", "carte": "Carte bancaire"}


class SandboxIndisponibleError(AppError):
    def __init__(self) -> None:
        super().__init__(code="NOT_FOUND", message="Ressource introuvable.", status_code=404)


class PageDePaiementInvalideError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="PAGE_DE_PAIEMENT_INVALIDE",
            message="Cette page de paiement est invalide ou a expiré.",
            status_code=400,
        )


def get_webhook_deliverer(
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebhookDeliverer:
    """Livraison HTTP réelle de la notification (surchargée dans les tests)."""

    async def deliver(url: str, body: bytes, headers: dict[str, str]) -> int:
        async with httpx.AsyncClient(timeout=settings.payment_provider_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=headers)
            return response.status_code

    return deliver


def _sandbox(provider: PaymentProvider | None) -> SandboxProvider:
    if not isinstance(provider, SandboxProvider):
        raise SandboxIndisponibleError()
    return provider


def _claims(provider: SandboxProvider, token: str) -> dict[str, Any]:
    try:
        return provider.read_checkout_token(token)
    except InvalidWebhookSignatureError as exc:
        raise PageDePaiementInvalideError() from exc


def _webhook_url(settings: Settings) -> str:
    return (
        settings.sandbox_webhook_url
        or f"{settings.backend_public_base_url.rstrip('/')}/api/v1/webhooks/payments"
    )


def _format_fcfa(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " FCFA"


def _security_headers(settings: Settings) -> dict[str, str]:
    front = settings.frontend_public_base_url.rstrip("/")
    return {
        # Page autonome : aucun script, styles en ligne, formulaire vers
        # elle-même puis redirection vers le front uniquement.
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; "
            f"form-action 'self' {front}; frame-ancestors 'none'; base-uri 'none'"
        ),
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }


@router.get("/checkout/{token}", response_class=HTMLResponse)
async def checkout_page(
    token: str,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[PaymentProvider | None, Depends(get_payment_provider)],
) -> HTMLResponse:
    claims = _claims(_sandbox(provider), token)
    amount = _format_fcfa(int(claims["amt"]))
    channel = html.escape(_CHANNEL_LABELS.get(str(claims["ch"]), str(claims["ch"])))
    description = html.escape(str(claims["desc"]))
    expires = datetime.fromtimestamp(int(claims["exp"]), tz=UTC).strftime("%H:%M UTC")
    action = html.escape(f"/api/v1/sandbox/checkout/{token}", quote=True)
    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paiement sandbox</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f4f1ea;color:#1c1917;margin:0;padding:16px}}
main{{max-width:420px;margin:24px auto;background:#fff;border-radius:16px;padding:24px;
box-shadow:0 4px 24px rgba(0,0,0,.08)}}
.badge{{display:inline-block;background:#fde68a;border-radius:999px;padding:2px 10px;
font-size:12px;font-weight:700}}
.amount{{font-size:32px;font-weight:800;margin:8px 0}}
button{{width:100%;padding:14px;border:0;border-radius:999px;font-size:16px;
font-weight:700;margin-top:12px;cursor:pointer}}
.pay{{background:#0b5d3b;color:#fff}} .fail{{background:#fee2e2;color:#991b1b}}
label{{display:flex;gap:8px;align-items:flex-start;font-size:14px;margin-top:16px}}
p{{line-height:1.5}} small{{color:#57534e}}
</style></head><body><main>
<span class="badge">SANDBOX — aucun argent réel</span>
<p>{description}<br><small>Moyen choisi : {channel}</small></p>
<p class="amount">{amount}</p>
<small>Page valable jusqu'à {expires}.</small>
<form method="post" action="{action}">
<label><input type="checkbox" name="replay" value="1">
Livrer la notification deux fois (vérifier l'idempotence du webhook)</label>
<button class="pay" name="outcome" value="paye">Payer {amount}</button>
<button class="fail" name="outcome" value="echoue">Simuler un échec</button>
</form></main></body></html>"""
    return HTMLResponse(page, headers=_security_headers(settings))


@router.post("/checkout/{token}")
async def submit_checkout(
    token: str,
    outcome: Annotated[Literal["paye", "echoue"], Form()],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[PaymentProvider | None, Depends(get_payment_provider)],
    deliver: Annotated[WebhookDeliverer, Depends(get_webhook_deliverer)],
    replay: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    sandbox = _sandbox(provider)
    claims = _claims(sandbox, token)
    sandbox_outcome: SandboxOutcome = outcome
    body = sandbox.build_event(claims, sandbox_outcome)
    # Le même événement (même event id) livré une ou deux fois : la seconde
    # livraison doit être un no-op côté webhook.
    for _ in range(2 if replay else 1):
        headers = {"Content-Type": "application/json", SIGNATURE_HEADER: sandbox.sign(body)}
        try:
            status = await deliver(_webhook_url(settings), body, headers)
            logger.info("Sandbox : notification livrée (HTTP %s).", status)
        except httpx.HTTPError as exc:
            # Comme chez un vrai fournisseur, l'échec de livraison n'empêche
            # pas le retour du client ; le front affiche alors « en attente ».
            logger.warning("Sandbox : livraison du webhook impossible : %s", exc)
    target = claims["ok"] if outcome == "paye" else claims["ko"]
    return RedirectResponse(str(target), status_code=303, headers=_security_headers(settings))
