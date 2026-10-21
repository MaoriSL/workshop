"""
Modèle ORM du service d'authentification (schéma PostgreSQL "auth").

La table users contient les mots de passe HASHÉS (Argon2). Les autres services
n'y accèdent jamais : ils ne voient que la vue auth.user_directory (id, email, name),
créée par la migration 0001 et accordée en lecture seule au rôle poupal_api.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    # Email stocké en minuscules ; unicité garantie par la base
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
