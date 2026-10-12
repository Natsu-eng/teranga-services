"""En-têtes de sécurité HTTP posés sur TOUTES les réponses (DEPLOYMENT.md,
durcissement).

Middleware ASGI pur (pas `BaseHTTPMiddleware`) : il ne touche qu'au message
`http.response.start`, sans bufferiser le corps -- les réponses en flux
(documents, pièces jointes) passent telles quelles, et les WebSockets ne
sont jamais concernées.

**Une route qui fixe déjà un en-tête le garde** (`setdefault`) : la page de
paiement sandbox a sa propre CSP (formulaire vers le front), plus précise que
la politique générale de l'API.

Politique : l'API ne sert que du JSON et des images -- elle n'a besoin
d'aucun script, d'aucun cadre, d'aucune fonctionnalité du navigateur. La CSP
par défaut interdit donc tout (`default-src 'none'`). Seule exception, hors
production : la documentation interactive (/docs, /redoc), qui charge
Swagger UI / ReDoc depuis jsDelivr ; en production cette documentation est
désactivée (app/main.py), l'exception ne s'applique donc jamais.

HSTS (HTTPS obligatoire pour le navigateur) n'est envoyé qu'en production :
en local, il « collerait » le HTTPS à localhost pour tous les projets du
développeur.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# Swagger UI et ReDoc (FastAPI) : scripts et styles jsDelivr, script en ligne
# d'initialisation, favicon FastAPI. Jamais servi en production.
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "connect-src 'self'; worker-src blob:; "
    "frame-ancestors 'none'; base-uri 'none'"
)
DOCS_PATHS = ("/docs", "/redoc")
# Deux ans, sous-domaines compris. Pas de `preload` : c'est un engagement
# (liste des navigateurs) à prendre sciemment, documenté dans DEPLOYMENT.md.
HSTS = "max-age=63072000; includeSubDomains"

BASE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=()"
    ),
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, production: bool, docs_enabled: bool) -> None:
        self._app = app
        self._production = production
        self._docs_enabled = docs_enabled

    def _csp_for(self, path: str) -> str:
        if self._docs_enabled and path.startswith(DOCS_PATHS):
            return DOCS_CSP
        return API_CSP

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        csp = self._csp_for(scope.get("path", ""))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in BASE_HEADERS.items():
                    headers.setdefault(name, value)
                headers.setdefault("Content-Security-Policy", csp)
                if self._production:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        await self._app(scope, receive, send_with_headers)
