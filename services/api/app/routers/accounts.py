"""
Routes des comptes : GET /api/accounts/me (Bearer obligatoire).
Le compte est créé à la première consultation, avec le solde de démonstration.
"""
from fastapi import APIRouter

from ..deps import CurrentUserDep, DbDep
from ..schemas import AccountOut
from ..services.accounts import get_or_create_account

router = APIRouter(prefix="/api/accounts", tags=["comptes"])


@router.get("/me", response_model=AccountOut, summary="Mon compte (créé automatiquement s'il n'existe pas)")
def read_my_account(user: CurrentUserDep, db: DbDep) -> AccountOut:
    account = get_or_create_account(db, user.id)
    db.commit()
    return AccountOut(
        account_id=account.id,
        user_id=account.user_id,
        balance_cents=account.balance_cents,
        currency=account.currency,
        opening_balance_cents=account.opening_balance_cents,
        created_at=account.created_at,
    )
