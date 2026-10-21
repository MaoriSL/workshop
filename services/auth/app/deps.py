"""
Dépendances FastAPI du service auth : identification de l'utilisateur courant à partir
du jeton Bearer. Une route protégée déclare simplement `user: User = Depends(get_current_user)`.

Règle : toute anomalie (jeton absent, mal formé, signature invalide, expiré, compte
disparu) donne le MÊME 401 `invalid_token` ; le détail ne va que dans les logs.
"""
from __future__ import annotations

import logging
import uuid

import jwt
from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .core.database import get_db
from .core.errors import AppError
from .core.logging import log_event, user_id_var
from .core.secrets import SecretUnavailableError
from .models import User
from .security import decode_access_token

# auto_error=False : on produit nous-mêmes le 401 au format {"message","code"} du projet
bearer_scheme = HTTPBearer(auto_error=False, description="Jeton obtenu via POST /auth/login")


def unauthorized() -> AppError:
    """401 uniforme, avec l'en-tête WWW-Authenticate attendu par les clients HTTP."""
    return AppError(401, "invalid_token", "Authentification requise.", headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Décode le jeton, charge l'utilisateur et renseigne user_id_var pour les logs.
    Dépendance async : le ContextVar posé ici reste visible par la route appelante
    (une dépendance sync s'exécute dans un thread avec une copie du contexte).
    """
    if credentials is None:
        raise unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        # Le motif (expiré, signature, émetteur...) est utile au SOC, pas au client
        log_event("token_rejected", logging.WARNING, reason=type(exc).__name__)
        raise unauthorized() from None
    except SecretUnavailableError:
        raise AppError(503, "service_unavailable", "Service temporairement indisponible.") from None

    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError:
        raise unauthorized() from None

    # Accès base (bloquant) exécuté dans le pool de threads pour ne pas figer la boucle d'événements
    user = await run_in_threadpool(db.get, User, user_id)
    if user is None:
        # Jeton correctement signé mais compte supprimé entre-temps : plus authentifié
        raise unauthorized()

    user_id_var.set(str(user.id))
    request.state.user_id = str(user.id)  # lu par le middleware pour le log d'accès
    return user
