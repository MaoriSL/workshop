"""
Schémas Pydantic du service d'authentification : ce qui entre (corps des requêtes)
et ce qui sort (réponses). La validation stricte se fait ici, avant toute logique métier.
Une requête non conforme reçoit un 422 au format {"message", "code", "errors"}.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .core.settings import settings

# Argon2 n'a pas de limite pratique, mais on refuse les mots de passe démesurés :
# hacher un corps de plusieurs Mo serait un vecteur de déni de service.
PASSWORD_MAX_LENGTH = 256


def _strip(value: object) -> object:
    """Retire les espaces de début/fin avant validation (longueur contrôlée sur la valeur nettoyée)."""
    return value.strip() if isinstance(value, str) else value


class RegisterIn(BaseModel):
    """Corps de POST /auth/register."""

    name: str = Field(min_length=2, max_length=80, examples=["Alex Martin"])
    email: EmailStr = Field(examples=["alex@poupal.demo"])
    password: str = Field(
        min_length=settings.password_min_length,
        max_length=PASSWORD_MAX_LENGTH,
        description=f"Au moins {settings.password_min_length} caractères.",
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        return _strip(value)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        """Un email est stocké et comparé en minuscules (unicité insensible à la casse)."""
        return value.lower()


class LoginIn(BaseModel):
    """Corps de POST /auth/login."""

    email: EmailStr = Field(examples=["alex@poupal.demo"])
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()


class UserOut(BaseModel):
    """Profil public d'un utilisateur (jamais le hash du mot de passe)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


class TokenOut(BaseModel):
    """Réponse de POST /auth/login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Durée de validité du jeton, en secondes.")


class ErrorOut(BaseModel):
    """Format d'erreur unique de la plateforme (sert à documenter l'OpenAPI)."""

    message: str
    code: str
