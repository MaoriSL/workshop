"""
API métier de paiement Poupal — point d'entrée FastAPI.

Rôle : comptes et transactions (montants en centimes, transferts atomiques).
L'API vérifie les JWT avec la clé PUBLIQUE uniquement : elle ne peut pas en émettre.
Observabilité : logs JSON, X-Request-ID, métriques Prometheus, /health, /ready,
et /internal/consistency (réseau Docker uniquement, bloqué par la gateway).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.errors import register_error_handlers
from .core.logging import configure_logging
from .core.metrics import DB_ERRORS, TRANSACTIONS
from .core.middleware import RequestContextMiddleware
from .core.settings import settings
from .routers import accounts, internal, tech, transactions

configure_logging(settings.service_name, settings.log_level)

# Séries métier initialisées à 0 dès le démarrage : les règles Prometheus (et les variables du
# modèle ML) existent avant le premier événement, au lieu d'apparaître à la première erreur.
DB_ERRORS.labels(settings.service_name)
for status in ("completed", "failed", "pending"):
    TRANSACTIONS.labels(status)

app = FastAPI(
    title="Poupal — API de paiement",
    description="Plateforme de paiement FICTIVE (environnement de démonstration, aucun paiement réel).",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware, service_name=settings.service_name)

register_error_handlers(app)

app.include_router(tech.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(internal.router)
