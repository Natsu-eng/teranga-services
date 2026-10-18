"""/api/v1/admin/diagnostics — Diagnostic d'exploitation, lecture seule.

`GET /admin/diagnostics/client-ip` : ce que le backend reçoit de la chaîne de
proxys de la plateforme, pour RÉGLER `TRUSTED_PROXY_HOPS` par la mesure
plutôt qu'en le devinant (DEPLOYMENT.md §12.7). Sans ce réglage juste, le
rate limiting par IP (OTP, triage IA) mettrait tous les clients dans un seul
compteur, ou laisserait un client falsifier son adresse.

Réservé aux admins (même garde que tout le back-office) ; ne renvoie que les
adresses de la requête de l'admin lui-même ; aucune écriture.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_role
from app.core.client_ip import client_ip
from app.core.config import Settings, get_settings
from app.models.enums import Role
from app.models.user import User
from app.schemas.admin_diagnostics import ClientIpDiagnosticOut

router = APIRouter()


@router.get("/diagnostics/client-ip", response_model=ClientIpDiagnosticOut)
async def client_ip_diagnostic(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    _admin: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> ClientIpDiagnosticOut:
    forwarded = [
        part.strip()
        for header in request.headers.getlist("x-forwarded-for")
        for part in header.split(",")
        if part.strip()
    ]
    return ClientIpDiagnosticOut(
        peer=request.client.host if request.client else None,
        x_forwarded_for=forwarded,
        trusted_proxy_hops=settings.trusted_proxy_hops or 0,
        client_ip=client_ip(request, settings),
    )
