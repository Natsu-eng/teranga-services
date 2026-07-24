"""Erreurs applicatives -> réponse JSON normalisée (BUILD_PLAN.md §3.1).

Format de sortie : `{ "error": { "code": ..., "message": ... } }`, avec un
`message` en français prêt à afficher (cohérent avec `ApiError` du front,
Lot 4). `AppError` peut être levée depuis n'importe quelle couche (service,
dépendance FastAPI, endpoint) ; `register_exception_handlers` branche la
conversion en réponse HTTP sur l'application.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Erreur métier porteuse d'un code machine, d'un message FR et d'un statut HTTP."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Branche la conversion de toute erreur (applicative ou FastAPI) au format §3.1."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(422, "VALIDATION_ERROR", "Requête invalide.")

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))
