"""
Journalisation JSON sur stdout (collectée plus tard par Loki).

Chaque ligne est un objet JSON : timestamp, level, service, request_id, user_id,
puis les champs propres à l'événement (event, method, route, status, latency_ms...).
Les identifiants de requête et d'utilisateur sont portés par des ContextVar :
n'importe quel log émis pendant une requête les inclut automatiquement.

Règle absolue : ne jamais logger de mot de passe, de jeton ni d'en-tête Authorization.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Contexte de requête (rempli par le middleware et la dépendance d'authentification)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

# Clés qu'on refuse de sérialiser, par sécurité, même si un appelant les passe par erreur.
_FORBIDDEN_FIELDS = {"password", "token", "access_token", "authorization", "password_hash"}

_service_name = "poupal"


class JsonFormatter(logging.Formatter):
    """Transforme un LogRecord en une ligne JSON compacte."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": _service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
        }
        # Champs supplémentaires passés via logger.info("...", extra={"fields": {...}})
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            for key, value in extra.items():
                if key.lower() in _FORBIDDEN_FIELDS:
                    continue
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Configure le logger racine : un seul handler JSON vers stdout."""
    global _service_name
    _service_name = service_name

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn a ses propres loggers : on les aligne sur notre format
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # L'access log d'uvicorn est remplacé par celui du middleware (plus riche)
    logging.getLogger("uvicorn.access").disabled = True


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Émet un événement métier structuré : log_event("login_failed", client_ip="...")."""
    logging.getLogger("poupal.events").log(level, event, extra={"fields": {"event": event, **fields}})
