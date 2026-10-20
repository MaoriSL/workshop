"""
Comptes de paiement : création à la demande, lecture et contrôle de cohérence.

Un compte est créé automatiquement la première fois qu'un utilisateur en a besoin
(consultation ou virement), avec le solde de démonstration. La création est
idempotente et sûre en concurrence : INSERT ... ON CONFLICT (user_id) DO NOTHING,
puis relecture. Les fonctions ne font jamais de commit : l'appelant décide.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..core.logging import log_event
from ..core.settings import settings
from ..models import Account, Transaction, TransactionStatus
from ..schemas import (
    ConsistencyChecks,
    ConsistencyReport,
    LedgerMismatch,
    NegativeBalancesCheck,
    PerAccountLedgerCheck,
    TotalConservationCheck,
)


def find_account(db: Session, user_id: uuid.UUID) -> Account | None:
    """Compte d'un utilisateur, ou None s'il n'en a pas encore."""
    return db.execute(select(Account).where(Account.user_id == user_id)).scalar_one_or_none()


def get_or_create_account(db: Session, user_id: uuid.UUID) -> Account:
    """
    Renvoie le compte de l'utilisateur, en le créant s'il n'existe pas (sans commit).

    Deux requêtes simultanées pour un même utilisateur ne créent qu'un seul compte :
    la contrainte UNIQUE(user_id) et ON CONFLICT DO NOTHING s'en chargent, sans erreur.
    """
    opening = settings.demo_initial_balance_cents
    statement = (
        insert(Account)
        .values(user_id=user_id, balance_cents=opening, opening_balance_cents=opening, currency=settings.currency)
        .on_conflict_do_nothing(index_elements=[Account.user_id])
    )
    inserted = db.execute(statement).rowcount
    if inserted:
        log_event("account_created", user_id=str(user_id), opening_balance_cents=opening)
    # Relecture : la ligne existe désormais, qu'elle vienne de nous ou d'une requête concurrente
    return db.execute(select(Account).where(Account.user_id == user_id)).scalar_one()


def consistency_report(db: Session) -> ConsistencyReport:
    """
    Contrôle de cohérence du ledger (GET /internal/consistency) :
      - aucun solde négatif ;
      - conservation du total : Σ soldes = Σ soldes d'ouverture (les virements sont internes) ;
      - par compte : ouverture + Σ reçues (completed) − Σ envoyées (completed) = solde.
    """
    # Un seul instantané pour toutes les lectures : un virement validé pendant le contrôle
    # ne peut pas produire une fausse incohérence (doit précéder la première requête SQL).
    db.connection(execution_options={"isolation_level": "REPEATABLE READ"})

    negative_count = db.execute(select(func.count()).select_from(Account).where(Account.balance_cents < 0)).scalar_one()

    sums = db.execute(
        select(
            func.coalesce(func.sum(Account.balance_cents), 0),
            func.coalesce(func.sum(Account.opening_balance_cents), 0),
        )
    ).one()
    sum_balances, sum_opening = int(sums[0]), int(sums[1])

    completed = Transaction.status == TransactionStatus.completed
    sent_by_account = dict(
        db.execute(
            select(Transaction.sender_account_id, func.sum(Transaction.amount_cents))
            .where(completed)
            .group_by(Transaction.sender_account_id)
        ).all()
    )
    received_by_account = dict(
        db.execute(
            select(Transaction.recipient_account_id, func.sum(Transaction.amount_cents))
            .where(completed)
            .group_by(Transaction.recipient_account_id)
        ).all()
    )

    mismatches: list[LedgerMismatch] = []
    for account in db.execute(select(Account)).scalars():
        expected = (
            account.opening_balance_cents
            + int(received_by_account.get(account.id, 0))
            - int(sent_by_account.get(account.id, 0))
        )
        if expected != account.balance_cents:
            mismatches.append(LedgerMismatch(account_id=account.id, expected_cents=expected, actual_cents=account.balance_cents))

    checks = ConsistencyChecks(
        negative_balances=NegativeBalancesCheck(ok=negative_count == 0, count=negative_count),
        total_conservation=TotalConservationCheck(
            ok=sum_balances == sum_opening,
            sum_balances_cents=sum_balances,
            sum_opening_balances_cents=sum_opening,
        ),
        per_account_ledger=PerAccountLedgerCheck(ok=not mismatches, mismatches=mismatches),
    )
    ok = checks.negative_balances.ok and checks.total_conservation.ok and checks.per_account_ledger.ok
    log_event(
        "consistency_checked",
        level=logging.INFO if ok else logging.WARNING,
        status="ok" if ok else "ko",
        negative_balances=negative_count,
        ledger_mismatches=len(mismatches),
    )
    return ConsistencyReport(status="ok" if ok else "ko", checks=checks, checked_at=datetime.now(timezone.utc))
