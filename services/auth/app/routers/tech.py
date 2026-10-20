"""
Endpoints techniques, identiques sur tous les services Poupal :
  GET /health  → liveness  : le processus répond (toujours 200).
  GET /ready   → readiness : base joignable ET secrets chargés (503 sinon).
  GET /metrics → métriques Prometheus (format texte).
"""
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from ..core.database import check_database
from ..core.metrics import render_metrics
from ..core.secrets import secrets_available
from ..core.settings import settings

router = APIRouter(tags=["technique"])


@router.get("/health", summary="Liveness")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@router.get("/ready", summary="Readiness (base + secrets)")
def ready() -> JSONResponse:
    checks = {"database": check_database(), "secrets": secrets_available()}
    ok = all(checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "ko", "service": settings.service_name, "checks": checks},
    )


@router.get("/metrics", summary="Métriques Prometheus", include_in_schema=False)
def metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
