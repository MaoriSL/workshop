"""
Routes internes, SANS authentification : réservées au réseau Docker.
La gateway renvoie 403 sur /internal/ ; seuls la supervision et le moteur de
remédiation (même réseau) peuvent appeler ces routes.

  GET /internal/consistency  rapport de cohérence du ledger (toujours HTTP 200 :
                             "ok" ou "ko" dans le corps). Si la base est injoignable,
                             le gestionnaire commun répond 503 database_error.
"""
from fastapi import APIRouter

from ..deps import DbDep
from ..schemas import ConsistencyReport
from ..services.accounts import consistency_report

router = APIRouter(prefix="/internal", tags=["interne (réseau Docker uniquement)"])


@router.get("/consistency", response_model=ConsistencyReport, summary="Contrôle de cohérence du ledger")
def check_consistency(db: DbDep) -> ConsistencyReport:
    return consistency_report(db)
