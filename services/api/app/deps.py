"""
Dépendances FastAPI de l'API métier.

Authentification : l'API vérifie les jetons émis par le service auth avec la clé
PUBLIQUE uniquement (RS256) ; elle ne peut pas en fabriquer et ne consulte jamais
auth.users. L'utilisateur courant est reconstruit à partir des claims du jeton.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .core.database import get_db
from .core.errors import AppError
from .core.logging import log_event, user_id_var
from .core.secrets import SecretUnavailableError, load_jwt_public_key
from .core.settings import settings

# auto_error=False : c'est nous qui renvoyons le 401, au format d'erreur unique {"message","code"}
bearer_scheme = HTTPBearer(auto_error=False, description="Jeton JWT délivré par POST /auth/login")


@dataclass(frozen=True)
class CurrentUser:
    """Utilisateur authentifié, issu des claims du JWT (aucun accès à la base auth)."""

    id: uuid.UUID
    email: str
    name: str


def unauthorized() -> AppError:
    """401 standard : jeton absent, invalide ou expiré (même réponse dans les trois cas)."""
    return AppError(401, "invalid_token", "Authentification requise.", headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    """
    Vérifie le Bearer et renvoie l'utilisateur courant.

    Dépendance asynchrone volontairement : elle s'exécute dans le contexte de la requête,
    si bien que le user_id posé ici est visible par les logs métier émis par les endpoints
    (une dépendance synchrone tournerait dans un thread avec une copie du contexte).
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise unauthorized()

    try:
        public_key = load_jwt_public_key()
    except SecretUnavailableError as exc:
        # Erreur de configuration côté serveur, pas côté client : 503 + log, sans détail dans la réponse
        log_event("jwt_public_key_unavailable", level=logging.ERROR, error=str(exc))
        raise AppError(503, "service_unavailable", "Service temporairement indisponible.") from exc

    try:
        claims = jwt.decode(
            credentials.credentials,
            public_key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
        user_id = uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        # Signature, émetteur, expiration ou sujet invalides : même réponse, rien de plus
        raise unauthorized() from None

    user_id_var.set(str(user_id))
    request.state.user_id = str(user_id)  # disponible pour le middleware (scope partagé)
    return CurrentUser(id=user_id, email=str(claims.get("email", "")), name=str(claims.get("name", "")))


# Raccourcis d'annotation pour les routeurs
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
DbDep = Annotated[Session, Depends(get_db)]
