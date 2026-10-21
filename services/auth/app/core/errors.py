"""
Format d'erreur unique côté client : {"message": "...", "code": "..."}.
Le détail technique (stack trace) reste dans les logs, jamais dans la réponse.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException  # classe parente : couvre aussi les 404/405 du routeur

from .metrics import DB_ERRORS
from .settings import settings

logger = logging.getLogger("poupal.errors")


class AppError(HTTPException):
    """Erreur applicative avec un code stable (ex. "invalid_credentials")."""

    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.message, "code": exc.code},
            headers=exc.headers,
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
        # Erreurs FastAPI génériques (404 route inconnue, 405...)
        message = exc.detail if isinstance(exc.detail, str) else "Erreur de requête."
        return JSONResponse(status_code=exc.status_code, content={"message": message, "code": "http_error"}, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"message": "Requête invalide.", "code": "validation_error", "errors": errors},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        DB_ERRORS.labels(settings.service_name).inc()
        logger.error("database_error", exc_info=exc, extra={"fields": {"event": "database_error"}})
        return JSONResponse(status_code=503, content={"message": "Service temporairement indisponible.", "code": "database_error"})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", exc_info=exc, extra={"fields": {"event": "unhandled_error"}})
        return JSONResponse(status_code=500, content={"message": "Erreur interne.", "code": "internal_error"})
