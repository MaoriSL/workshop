"""
Middleware de contexte de requête :
  - propage ou génère X-Request-ID (renvoyé dans la réponse) ;
  - mesure la latence et alimente les métriques Prometheus ;
  - émet le log d'accès JSON (method, route, status, latency_ms, user_id, client_ip).

La route est enregistrée sous sa forme "template" (/api/transactions/{transaction_id})
pour ne pas faire exploser le nombre de séries Prometheus.
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .logging import request_id_var, user_id_var
from .metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS

access_logger = logging.getLogger("poupal.access")

REQUEST_ID_HEADER = "X-Request-ID"


def get_client_ip(request: Request) -> str:
    """IP du client. Uvicorn (--proxy-headers) a déjà appliqué X-Forwarded-For
    envoyé par la gateway ; request.client reflète donc l'IP réelle."""
    return request.client.host if request.client else "unknown"


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service_name: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming[:64] if incoming else str(uuid.uuid4())
        request.state.request_id = request_id
        token_rid = request_id_var.set(request_id)
        token_uid = user_id_var.set(None)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            route = route_template(request)
            method = request.method

            HTTP_REQUESTS.labels(self.service_name, method, route, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(self.service_name, method, route).observe(latency_ms / 1000)

            # L'utilisateur est posé par la dépendance d'authentification dans request.state
            # (scope partagé) : fiable même si la ContextVar a été modifiée dans une sous-tâche.
            user_id = request.scope.get("state", {}).get("user_id") or user_id_var.get()

            # Pas de log d'accès pour les sondes techniques (bruit inutile)
            if route not in ("/health", "/ready", "/metrics"):
                access_logger.info(
                    "http_request",
                    extra={
                        "fields": {
                            "event": "http_request",
                            "method": method,
                            "route": route,
                            "path": request.url.path,
                            "status": status_code,
                            "latency_ms": latency_ms,
                            "user_id": user_id,
                            "client_ip": get_client_ip(request),
                        }
                    },
                )
            user_id_var.reset(token_uid)
            request_id_var.reset(token_rid)
