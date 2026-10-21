"""
Service d'authentification Poupal — point d'entrée FastAPI.

Rôle : inscription, connexion (JWT RS256 signé avec la clé privée), profil.
Observabilité : logs JSON, X-Request-ID, métriques Prometheus, /health et /ready.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.errors import register_error_handlers
from .core.logging import configure_logging
from .core.metrics import DB_ERRORS, LOGIN_ATTEMPTS
from .core.middleware import RequestContextMiddleware
from .core.settings import settings
from .routers import auth, tech

configure_logging(settings.service_name, settings.log_level)

# Séries métier initialisées à 0 dès le démarrage : les règles Prometheus (et les variables du
# modèle ML) existent avant le premier événement, au lieu d'apparaître à la première erreur.
DB_ERRORS.labels(settings.service_name)
for result in ("success", "failure", "rate_limited"):
    LOGIN_ATTEMPTS.labels(result)

app = FastAPI(
    title="Poupal — Service d'authentification",
    description="Plateforme de paiement FICTIVE (environnement de démonstration, aucune donnée réelle).",
    version="0.1.0",
    docs_url="/auth/docs",
    openapi_url="/auth/openapi.json",
)

# CORS limité à l'origine du front (variable CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
# Contexte de requête (X-Request-ID, métriques, log d'accès) — ajouté en dernier = exécuté en premier
app.add_middleware(RequestContextMiddleware, service_name=settings.service_name)

register_error_handlers(app)

app.include_router(tech.router)
app.include_router(auth.router)
