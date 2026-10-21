"""
Virements entre comptes Poupal : logique métier de POST /api/transactions,
plus la consultation de l'historique (liste paginée, détail) et la mise en forme
des transactions du point de vue de l'utilisateur courant.

Garanties :
  - atomicité : les deux comptes sont verrouillés (SELECT ... FOR UPDATE) dans l'ordre
    de leur id — ordre constant, donc pas d'interblocage — puis débit, crédit et
    enregistrement de la transaction ont lieu dans la MÊME transaction SQL ;
  - un solde ne devient jamais négatif (contrôle ici + contrainte CHECK en base) ;
  - un solde insuffisant laisse une trace : transaction "failed" (failure_reason) ;
  - idempotence : une Idempotency-Key rejouée avec le même corps renvoie la réponse
    mémorisée (200) ; rejouée avec un corps différent, elle est refusée (422) ;
  - limitation de débit par utilisateur (429 + Retry-After).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Sequence, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import AppError
from ..core.logging import log_event
from ..core.metrics import TRANSACTION_AMOUNT, TRANSACTIONS
from ..core.rate_limit import RateLimiter
from ..core.settings import settings
from ..deps import CurrentUser
from ..models import Account, IdempotencyKey, Transaction, TransactionStatus, UserDirectory
from ..schemas import CounterpartyOut, TransactionCreate, TransactionOut
from .accounts import find_account, get_or_create_account

# Limiteur partagé par toutes les requêtes du processus (clé = id utilisateur). Les tests appellent .reset().
transaction_limiter = RateLimiter(settings.transaction_rate_limit)

# Séquence SQL des références lisibles : PP-2026-000412
reference_sequence = Sequence("transaction_reference_seq", schema="payments")

UNKNOWN_USER_NAME = "Utilisateur inconnu"


@dataclass(frozen=True)
class TransferResult:
    transaction: Transaction
    status_code: int  # 201 à la création, 200 lors d'un rejeu idempotent


# ---------------------------------------------------------------- Utilitaires
def insufficient_funds_error() -> AppError:
    return AppError(422, "insufficient_funds", "Solde insuffisant.")


def transaction_not_found_error() -> AppError:
    return AppError(404, "transaction_not_found", "Transaction introuvable.")


def format_euros(cents: int) -> str:
    """500000 → "5 000,00 €" (format français, pour les messages d'erreur)."""
    euros, reste = divmod(cents, 100)
    return f"{euros:,}".replace(",", " ") + f",{reste:02d} €"


def request_fingerprint(payload: TransactionCreate) -> str:
    """Empreinte SHA-256 du JSON canonique du corps : détecte une clé réutilisée avec un autre corps."""
    canonical = json.dumps(
        {"recipient_email": payload.recipient_email, "amount_cents": payload.amount_cents, "message": payload.message},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def next_reference(db: Session) -> str:
    """Référence suivante, tirée de la séquence SQL (jamais réutilisée, même après un rollback)."""
    number = db.execute(select(reference_sequence.next_value())).scalar_one()
    return f"PP-{datetime.now(timezone.utc).year}-{number:06d}"


# ---------------------------------------------------------------- Virement
def create_transfer(db: Session, user: CurrentUser, payload: TransactionCreate, idempotency_key: str) -> TransferResult:
    """
    Exécute un virement de l'utilisateur courant vers `payload.recipient_email`.
    Les règles sont appliquées dans l'ordre du contrat d'API (le routeur a déjà
    vérifié la présence de l'en-tête Idempotency-Key).
    """
    # 2. Limitation de débit par utilisateur
    allowed, retry_after = transaction_limiter.allow(str(user.id))
    if not allowed:
        log_event("transaction_rate_limited", sender_id=str(user.id), retry_after=retry_after)
        raise AppError(
            429, "rate_limited", "Trop de tentatives. Réessayez dans un instant.", headers={"Retry-After": str(retry_after)}
        )

    # 3. Idempotence : clé déjà vue pour cet utilisateur → rejeu (ou refus si le corps diffère)
    fingerprint = request_fingerprint(payload)
    stored = db.get(IdempotencyKey, {"user_id": user.id, "key": idempotency_key})
    if stored is not None:
        return replay(db, stored, fingerprint)

    # 4. Plafond par virement
    if payload.amount_cents > settings.max_transaction_cents:
        raise AppError(422, "amount_too_large", f"Le montant maximal est de {format_euros(settings.max_transaction_cents)}.")

    # 5. Destinataire : uniquement via l'annuaire (vue en lecture seule du schéma auth)
    recipient = db.execute(select(UserDirectory).where(UserDirectory.email == payload.recipient_email)).scalar_one_or_none()
    if recipient is None:
        raise AppError(404, "recipient_not_found", "Destinataire introuvable.")

    # 6. Pas de virement vers soi-même
    if recipient.id == user.id:
        raise AppError(422, "self_transfer", "Impossible de s'envoyer de l'argent à soi-même.")

    # 7. Comptes créés si absents, toujours dans le même ordre (évite un interblocage
    #    si deux virements croisés créent les deux comptes au même instant)
    accounts = {user_id: get_or_create_account(db, user_id) for user_id in sorted((user.id, recipient.id))}
    sender_id, recipient_id = accounts[user.id].id, accounts[recipient.id].id

    # 8. Section critique : verrouillage des DEUX comptes dans l'ordre des id.
    #    populate_existing : on relit les soldes verrouillés (jamais ceux déjà en cache dans la session).
    locked = db.execute(
        select(Account)
        .where(Account.id.in_([sender_id, recipient_id]))
        .order_by(Account.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalars()
    by_id = {account.id: account for account in locked}
    sender_account, recipient_account = by_id[sender_id], by_id[recipient_id]

    if sender_account.balance_cents < payload.amount_cents:
        status, status_code, failure_reason = TransactionStatus.failed, 422, "insufficient_funds"
    else:
        status, status_code, failure_reason = TransactionStatus.completed, 201, None
        sender_account.balance_cents -= payload.amount_cents
        recipient_account.balance_cents += payload.amount_cents

    transaction = Transaction(
        reference=next_reference(db),
        sender_account_id=sender_id,
        recipient_account_id=recipient_id,
        amount_cents=payload.amount_cents,
        currency=settings.currency,
        status=status,
        failure_reason=failure_reason,
        message=payload.message,
    )
    db.add(transaction)
    db.flush()  # obtient transaction.id pour la clé d'idempotence
    db.add(
        IdempotencyKey(
            user_id=user.id,
            key=idempotency_key,
            request_hash=fingerprint,
            transaction_id=transaction.id,
            status_code=status_code,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Deux requêtes simultanées avec la même clé : la première a gagné (clé primaire),
        # on annule notre tentative et on rejoue sa réponse. Toute autre cause remonte en 503.
        db.rollback()
        winner = db.get(IdempotencyKey, {"user_id": user.id, "key": idempotency_key})
        if winner is None:
            raise
        return replay(db, winner, fingerprint)

    TRANSACTIONS.labels(status.value).inc()
    if status is TransactionStatus.completed:
        TRANSACTION_AMOUNT.observe(payload.amount_cents)
        log_event(
            "transaction_completed",
            transaction_id=str(transaction.id),
            reference=transaction.reference,
            amount_cents=payload.amount_cents,
            sender_id=str(user.id),
            recipient_id=str(recipient.id),
        )
        return TransferResult(transaction=transaction, status_code=201)

    log_event(
        "transaction_failed",
        reason="insufficient_funds",
        transaction_id=str(transaction.id),
        reference=transaction.reference,
        amount_cents=payload.amount_cents,
        sender_id=str(user.id),
        recipient_id=str(recipient.id),
    )
    raise insufficient_funds_error()


def replay(db: Session, stored: IdempotencyKey, fingerprint: str) -> TransferResult:
    """Rejoue la réponse mémorisée pour une clé d'idempotence déjà utilisée."""
    if stored.request_hash != fingerprint:
        raise AppError(422, "idempotency_key_reused", "Clé d'idempotence déjà utilisée avec une requête différente.")
    if stored.status_code != 201 or stored.transaction_id is None:
        # Le premier essai s'était soldé par un solde insuffisant : même réponse
        raise insufficient_funds_error()
    transaction = db.get(Transaction, stored.transaction_id)
    if transaction is None:  # impossible grâce à la clé étrangère ; on reste défensif
        raise AppError(500, "internal_error", "Erreur interne.")
    log_event("transaction_replayed", transaction_id=str(transaction.id), reference=transaction.reference)
    return TransferResult(transaction=transaction, status_code=200)


# ---------------------------------------------------------------- Consultation
def list_transactions(db: Session, user_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Transaction], int]:
    """Transactions envoyées ET reçues par l'utilisateur, plus récentes en premier, avec le total."""
    account = find_account(db, user_id)
    if account is None:
        return [], 0
    involves_user = or_(Transaction.sender_account_id == account.id, Transaction.recipient_account_id == account.id)
    total = db.execute(select(func.count()).select_from(Transaction).where(involves_user)).scalar_one()
    items = db.execute(
        select(Transaction)
        .where(involves_user)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(items), total


def get_transaction_for_user(db: Session, user_id: uuid.UUID, transaction_id: str) -> Transaction:
    """Détail d'une transaction si l'utilisateur en est l'émetteur ou le destinataire, sinon 404
    (jamais 403 : on ne révèle pas l'existence d'une transaction d'un tiers)."""
    try:
        wanted_id = uuid.UUID(transaction_id)
    except ValueError:
        raise transaction_not_found_error() from None
    account = find_account(db, user_id)
    if account is None:
        raise transaction_not_found_error()
    transaction = db.execute(
        select(Transaction).where(
            Transaction.id == wanted_id,
            or_(Transaction.sender_account_id == account.id, Transaction.recipient_account_id == account.id),
        )
    ).scalar_one_or_none()
    if transaction is None:
        raise transaction_not_found_error()
    return transaction


def to_transaction_out(db: Session, transactions: list[Transaction], user_id: uuid.UUID) -> list[TransactionOut]:
    """Met en forme des transactions du point de vue de `user_id` : type sent/received + contrepartie."""

    def counterparty_user_id(transaction: Transaction) -> uuid.UUID:
        return transaction.recipient.user_id if transaction.sender.user_id == user_id else transaction.sender.user_id

    # Les contreparties sont lues dans l'annuaire en une seule requête
    directory: dict[uuid.UUID, UserDirectory] = {}
    wanted = {counterparty_user_id(transaction) for transaction in transactions}
    if wanted:
        rows = db.execute(select(UserDirectory).where(UserDirectory.id.in_(wanted))).scalars()
        directory = {row.id: row for row in rows}

    result: list[TransactionOut] = []
    for transaction in transactions:
        other_id = counterparty_user_id(transaction)
        entry = directory.get(other_id)
        result.append(
            TransactionOut(
                id=transaction.id,
                reference=transaction.reference,
                type="sent" if transaction.sender.user_id == user_id else "received",
                status=transaction.status,
                amount_cents=transaction.amount_cents,
                currency=transaction.currency,
                message=transaction.message,
                failure_reason=transaction.failure_reason,
                counterparty=CounterpartyOut(
                    user_id=other_id,
                    email=entry.email if entry else None,
                    name=entry.name if entry else UNKNOWN_USER_NAME,
                ),
                created_at=transaction.created_at,
            )
        )
    return result
