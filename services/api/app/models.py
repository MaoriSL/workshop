"""
Modèles ORM de l'API métier (schéma PostgreSQL "payments").

Règles structurantes :
  - les montants sont des ENTIERS en centimes (jamais de float) ;
  - un solde ne peut pas être négatif (contrainte CHECK en base, en plus du code) ;
  - une transaction relie deux comptes ; son statut est completed, failed ou pending ;
  - l'annuaire des utilisateurs est une VUE en lecture seule du schéma auth.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.database import Base


class UserDirectory(Base):
    """Vue auth.user_directory (id, email, name) : lecture seule, jamais de mot de passe."""

    __tablename__ = "user_directory"
    __table_args__ = {"schema": "auth", "info": {"is_view": True}}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    name: Mapped[str] = mapped_column(String(80))


class TransactionStatus(str, enum.Enum):
    completed = "completed"
    failed = "failed"
    pending = "pending"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance_cents >= 0", name="ck_accounts_balance_non_negative"),
        {"schema": "payments"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    # Identifiant de l'utilisateur dans le schéma auth (pas de clé étrangère inter-schémas :
    # l'API n'a pas de droit sur auth.users ; l'annuaire garantit l'existence côté métier)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Solde initial offert à l'ouverture (démo) : sert au contrôle de cohérence
    opening_balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_transactions_amount_positive"),
        {"schema": "payments"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    # Référence lisible par le client, ex. PP-2026-000412 (séquence SQL)
    reference: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    sender_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.accounts.id"), nullable=False, index=True)
    recipient_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.accounts.id"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    status: Mapped[TransactionStatus] = mapped_column(Enum(TransactionStatus, name="transaction_status", schema="payments"), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(String(140), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    sender: Mapped[Account] = relationship(foreign_keys=[sender_account_id], lazy="joined")
    recipient: Mapped[Account] = relationship(foreign_keys=[recipient_account_id], lazy="joined")


class IdempotencyKey(Base):
    """Mémorise la réponse d'un POST /api/transactions pour une clé donnée (par utilisateur)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = {"schema": "payments"}

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Empreinte SHA-256 du corps de la requête : même clé + corps différent = erreur
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.transactions.id"), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
