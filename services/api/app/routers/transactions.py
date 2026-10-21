"""
Routes des transactions (Bearer obligatoire) :
  GET  /api/transactions                   historique paginé (envoyées et reçues)
  POST /api/transactions                   virement (en-tête Idempotency-Key obligatoire)
  GET  /api/transactions/{transaction_id}  détail (404 si l'utilisateur n'est pas concerné)
La logique métier est dans services/transfer.py ; ici on ne fait que brancher HTTP.
"""
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response

from ..core.errors import AppError
from ..deps import CurrentUserDep, DbDep
from ..schemas import TransactionCreate, TransactionOut, TransactionPage
from ..services.transfer import create_transfer, get_transaction_for_user, list_transactions, to_transaction_out

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=TransactionPage, summary="Historique de mes transactions")
def list_my_transactions(
    user: CurrentUserDep,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Taille de page (1 à 100)")] = 20,
    offset: Annotated[int, Query(ge=0, description="Décalage de départ")] = 0,
) -> TransactionPage:
    transactions, total = list_transactions(db, user.id, limit, offset)
    return TransactionPage(items=to_transaction_out(db, transactions, user.id), total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=TransactionOut,
    status_code=201,
    summary="Envoyer de l'argent",
    responses={200: {"description": "Rejeu idempotent : même Idempotency-Key et même corps", "model": TransactionOut}},
)
def send_money(
    payload: TransactionCreate,
    user: CurrentUserDep,
    db: DbDep,
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", max_length=128, description="Clé unique par tentative de virement (1 à 128 caractères)"),
    ] = None,
) -> TransactionOut:
    # Règle 1 du contrat : en-tête absent (ou vide) → 400, avant toute autre vérification
    key = (idempotency_key or "").strip()
    if not key:
        raise AppError(400, "idempotency_key_required", "L'en-tête Idempotency-Key est obligatoire.")

    result = create_transfer(db, user, payload, key)
    response.status_code = result.status_code  # 201 créée, 200 rejouée
    return to_transaction_out(db, [result.transaction], user.id)[0]


@router.get("/{transaction_id}", response_model=TransactionOut, summary="Détail d'une transaction")
def read_transaction(transaction_id: str, user: CurrentUserDep, db: DbDep) -> TransactionOut:
    # transaction_id est typé str : un UUID mal formé donne 404 (pas 422), comme une transaction inconnue
    transaction = get_transaction_for_user(db, user.id, transaction_id)
    return to_transaction_out(db, [transaction], user.id)[0]
