"""
Routes d'authentification : inscription, connexion (JWT RS256), profil.

Sécurité appliquée ici :
  - mot de passe haché avec Argon2, jamais stocké ni journalisé en clair ;
  - échec de connexion générique (même message pour email inconnu et mauvais mot de passe),
    avec vérification factice à temps constant quand l'email n'existe pas ;
  - limitation de débit sur /auth/login par IP client (429 + Retry-After) ;
  - événements structurés (login_success / login_failed / login_rate_limited /
    user_registered) et métrique LOGIN_ATTEMPTS pour la détection et le SOC.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.errors import AppError
from ..core.logging import log_event, user_id_var
from ..core.metrics import LOGIN_ATTEMPTS
from ..core.middleware import get_client_ip
from ..core.rate_limit import RateLimiter
from ..core.secrets import SecretUnavailableError
from ..core.settings import settings
from ..deps import get_current_user
from ..models import User
from ..schemas import ErrorOut, LoginIn, RegisterIn, TokenOut, UserOut
from ..security import (
    create_access_token,
    dummy_verify,
    hash_password,
    password_needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Un limiteur par processus : clé = IP client (fournie par la gateway via X-Forwarded-For)
login_limiter = RateLimiter(settings.login_rate_limit)


def _reject_login(email: str, client_ip: str, reason: str) -> AppError:
    """Échec de connexion : métrique, log (jamais le mot de passe) et 401 générique."""
    LOGIN_ATTEMPTS.labels("failure").inc()
    log_event("login_failed", logging.WARNING, email=email, client_ip=client_ip, reason=reason)
    return AppError(401, "invalid_credentials", "Email ou mot de passe incorrect.")


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    summary="Créer un compte",
    responses={409: {"model": ErrorOut, "description": "Email déjà utilisé"}},
)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> User:
    # Vérification lisible avant insertion ; la contrainte d'unicité de la base reste
    # l'arbitre final en cas de deux inscriptions simultanées (IntegrityError ci-dessous).
    already_used = db.scalar(select(User.id).where(User.email == payload.email)) is not None
    if already_used:
        raise AppError(409, "email_already_used", "Un compte existe déjà avec cet email.")

    user = User(email=payload.email, name=payload.name, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "email_already_used", "Un compte existe déjà avec cet email.") from None
    db.refresh(user)  # id et created_at sont générés par la base

    user_id_var.set(str(user.id))
    log_event("user_registered", user_id=str(user.id))
    return user


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Se connecter (jeton JWT)",
    responses={
        401: {"model": ErrorOut, "description": "Email ou mot de passe incorrect"},
        429: {"model": ErrorOut, "description": "Trop de tentatives (en-tête Retry-After)"},
    },
)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    client_ip = get_client_ip(request)

    # 1. Limitation de débit : toute tentative compte, réussie ou non
    allowed, retry_after = login_limiter.allow(client_ip)
    if not allowed:
        LOGIN_ATTEMPTS.labels("rate_limited").inc()
        log_event("login_rate_limited", logging.WARNING, client_ip=client_ip, retry_after=retry_after)
        raise AppError(
            429,
            "rate_limited",
            "Trop de tentatives. Réessayez dans un instant.",
            headers={"Retry-After": str(retry_after)},
        )

    # 2. Recherche du compte, puis vérification Argon2 (factice si l'email est inconnu)
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        dummy_verify(payload.password)
        raise _reject_login(payload.email, client_ip, "unknown_user")
    if not verify_password(user.password_hash, payload.password):
        raise _reject_login(payload.email, client_ip, "bad_password")

    # 3. Mise à niveau transparente du hash si les paramètres Argon2 ont été renforcés
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        db.commit()

    # 4. Émission du jeton signé avec la clé privée
    try:
        token, expires_in = create_access_token(user.id, user.email, user.name)
    except SecretUnavailableError:
        raise AppError(503, "service_unavailable", "Service temporairement indisponible.") from None

    user_id_var.set(str(user.id))
    LOGIN_ATTEMPTS.labels("success").inc()
    log_event("login_success", user_id=str(user.id), client_ip=client_ip)
    return TokenOut(access_token=token, expires_in=expires_in)


@router.get(
    "/me",
    response_model=UserOut,
    summary="Profil de l'utilisateur connecté",
    responses={401: {"model": ErrorOut, "description": "Jeton absent, invalide ou expiré"}},
)
def me(user: User = Depends(get_current_user)) -> User:
    return user
