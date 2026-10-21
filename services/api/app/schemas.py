"""
Schémas Pydantic de l'API métier : ce qui entre (validation stricte) et ce qui sort.

Conventions : JSON en snake_case, montants ENTIERS en centimes, dates ISO 8601 UTC.
Les objets ORM (models.py) ne sortent jamais tels quels : ils passent par ces schémas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import TransactionStatus


# ---------------------------------------------------------------- Comptes
class AccountOut(BaseModel):
    """Réponse de GET /api/accounts/me."""

    account_id: uuid.UUID
    user_id: uuid.UUID
    balance_cents: int
    currency: str
    opening_balance_cents: int
    created_at: datetime


# ---------------------------------------------------------------- Transactions
class TransactionCreate(BaseModel):
    """Corps de POST /api/transactions. Les champs inconnus sont refusés (contrat explicite)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient_email: EmailStr
    # strict=True : on refuse "100" (chaîne) ou 100.0 (flottant) — un montant est un entier de centimes
    amount_cents: int = Field(strict=True, gt=0, description="Montant en centimes, entier strictement positif")
    message: str | None = Field(default=None, max_length=140, description="Libellé facultatif (140 caractères max)")

    @field_validator("recipient_email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        # L'annuaire stocke les emails en minuscules : on normalise avant toute recherche
        return value.lower()

    @field_validator("message")
    @classmethod
    def empty_message_is_none(cls, value: str | None) -> str | None:
        # Un message vide (après suppression des espaces) est traité comme absent
        return value or None


class CounterpartyOut(BaseModel):
    """L'autre partie d'une transaction, vue par l'utilisateur courant."""

    user_id: uuid.UUID
    email: str | None  # null si l'utilisateur n'est plus dans l'annuaire
    name: str


class TransactionOut(BaseModel):
    """Une transaction, toujours relative à l'utilisateur courant (type sent / received)."""

    id: uuid.UUID
    reference: str
    type: Literal["sent", "received"]
    status: TransactionStatus
    amount_cents: int
    currency: str
    message: str | None
    failure_reason: str | None
    counterparty: CounterpartyOut
    created_at: datetime


class TransactionPage(BaseModel):
    """Page de l'historique : GET /api/transactions?limit=&offset=."""

    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------- Rapport de cohérence
class NegativeBalancesCheck(BaseModel):
    ok: bool
    count: int


class TotalConservationCheck(BaseModel):
    ok: bool
    sum_balances_cents: int
    sum_opening_balances_cents: int


class LedgerMismatch(BaseModel):
    account_id: uuid.UUID
    expected_cents: int
    actual_cents: int


class PerAccountLedgerCheck(BaseModel):
    ok: bool
    mismatches: list[LedgerMismatch]


class ConsistencyChecks(BaseModel):
    negative_balances: NegativeBalancesCheck
    total_conservation: TotalConservationCheck
    per_account_ledger: PerAccountLedgerCheck


class ConsistencyReport(BaseModel):
    """Réponse de GET /internal/consistency (toujours HTTP 200 : c'est un rapport)."""

    status: Literal["ok", "ko"]
    checks: ConsistencyChecks
    checked_at: datetime
