"""
Données de démonstration de l'API métier (SEED_DEMO_DATA=true) :  python -m app.seed

Idempotent, relancé à chaque démarrage du conteneur (entrypoint.sh) :
  - comptes des 10 utilisateurs de démo (créés côté auth par son propre seed), avec soldes d'ouverture ;
  - 12 transactions crédibles réparties sur les 30 derniers jours, dont 1 échouée (solde
    insuffisant) et 1 en attente ;
  - les soldes finaux respectent le ledger : solde = ouverture + Σ reçues − Σ envoyées (completed).
Ne crée pas un compte existant ; ne crée aucune transaction s'il en existe déjà
(les comptes manquants sont donc ajoutés même sur une base qui a déjà un historique).
Si les utilisateurs de démo manquent dans l'annuaire, affiche un message et sort avec 0.
Tout est FICTIF : environnement de démonstration, aucun paiement réel.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from .core.database import SessionLocal
from .core.logging import configure_logging, log_event
from .core.settings import settings
from .models import Account, Transaction, TransactionStatus, UserDirectory
from .services.transfer import next_reference

# Soldes d'ouverture en centimes (alex = 2 450,00 €, ...)
DEMO_ACCOUNTS: dict[str, int] = {
    "alex@poupal.demo": 245_000,
    "camille@poupal.demo": 180_000,
    "lea@poupal.demo": 320_000,
    "nathan@poupal.demo": 95_000,
    "julie@poupal.demo": 140_000,
    "hugo@poupal.demo": 60_000,
    # Ajoutés pour le générateur de trafic : pas d'historique de démo, ils en gagnent un en vivant
    "sophie@poupal.demo": 120_000,
    "lucas@poupal.demo": 90_000,
    "emma@poupal.demo": 150_000,
    "thomas@poupal.demo": 110_000,
}

# (jours avant aujourd'hui, émetteur, destinataire, montant en centimes, message, statut)
# Ordre chronologique : les références PP-... suivent l'ordre des dates.
DEMO_TRANSACTIONS: list[tuple[int, str, str, int, str, TransactionStatus]] = [
    (28, "alex", "camille", 65_000, "Loyer d'octobre — ma part", TransactionStatus.completed),
    (26, "lea", "nathan", 4_200, "Restaurant de vendredi soir", TransactionStatus.completed),
    (24, "camille", "julie", 3_500, "Remboursement courses", TransactionStatus.completed),
    (21, "nathan", "hugo", 12_000, "Cadeau commun pour Sarah", TransactionStatus.completed),
    (19, "hugo", "lea", 80_000, "Prêt pour le scooter", TransactionStatus.failed),  # Hugo n'a pas 800 €
    (17, "julie", "alex", 9_800, "Places de concert", TransactionStatus.completed),
    (14, "alex", "lea", 15_000, "Week-end à Lyon — hébergement", TransactionStatus.completed),
    (11, "camille", "nathan", 2_600, "Café et croissants", TransactionStatus.completed),
    (9, "lea", "camille", 23_000, "Billets de train", TransactionStatus.completed),
    (6, "hugo", "julie", 4_500, "Cinéma + popcorn", TransactionStatus.completed),
    (3, "nathan", "alex", 30_000, "Remboursement du prêt", TransactionStatus.completed),
    (1, "julie", "camille", 7_500, "Cadeau d'anniversaire", TransactionStatus.pending),
]


def email_of(short_name: str) -> str:
    return f"{short_name}@poupal.demo"


def main() -> int:
    configure_logging(settings.service_name, settings.log_level)

    with SessionLocal() as db:
        # 1. Les utilisateurs de démo doivent exister côté auth (vue en lecture seule)
        directory = {
            row.email: row
            for row in db.execute(select(UserDirectory).where(UserDirectory.email.in_(list(DEMO_ACCOUNTS)))).scalars()
        }
        missing = sorted(set(DEMO_ACCOUNTS) - set(directory))
        if missing:
            print(f"[seed api] utilisateurs absents de auth.user_directory : {', '.join(missing)}. "
                  "Lancez d'abord le seed du service auth. Rien à faire.")
            return 0

        # 2. Comptes : création idempotente (un compte existant garde son solde).
        #    Le nombre de comptes créés se mesure avant/après : rowcount n'est pas fiable
        #    pour un INSERT ... ON CONFLICT DO NOTHING selon le pilote.
        demo_user_ids = [directory[email].id for email in DEMO_ACCOUNTS]
        count_demo_accounts = select(func.count()).select_from(Account).where(Account.user_id.in_(demo_user_ids))
        before = db.scalar(count_demo_accounts) or 0
        for email, opening in DEMO_ACCOUNTS.items():
            statement = (
                insert(Account)
                .values(user_id=directory[email].id, balance_cents=opening, opening_balance_cents=opening, currency=settings.currency)
                .on_conflict_do_nothing(index_elements=[Account.user_id])
            )
            db.execute(statement)
        db.commit()
        created_accounts = (db.scalar(count_demo_accounts) or 0) - before
        log_event("seed_accounts", created=created_accounts)

        # 3. Transactions : uniquement si l'historique est vide
        existing = db.execute(select(func.count()).select_from(Transaction)).scalar_one()
        if existing:
            print(f"[seed api] {existing} transaction(s) déjà présente(s) : historique conservé.")
            return 0

        accounts = {
            email: db.execute(select(Account).where(Account.user_id == directory[email].id)).scalar_one()
            for email in DEMO_ACCOUNTS
        }
        now = datetime.now(timezone.utc)
        for index, (days_ago, sender, recipient, amount, message, status) in enumerate(DEMO_TRANSACTIONS):
            sender_account, recipient_account = accounts[email_of(sender)], accounts[email_of(recipient)]
            if status is TransactionStatus.completed:
                # Seules les transactions validées mouvementent les soldes (règle du ledger)
                sender_account.balance_cents -= amount
                recipient_account.balance_cents += amount
            db.add(
                Transaction(
                    reference=next_reference(db),
                    sender_account_id=sender_account.id,
                    recipient_account_id=recipient_account.id,
                    amount_cents=amount,
                    currency=settings.currency,
                    status=status,
                    failure_reason="insufficient_funds" if status is TransactionStatus.failed else None,
                    message=message,
                    # Heures et minutes variées pour un historique naturel
                    created_at=now - timedelta(days=days_ago, hours=(3 * index) % 9, minutes=(17 * index) % 60),
                )
            )

        negative = [email for email, account in accounts.items() if account.balance_cents < 0]
        if negative:
            db.rollback()
            print(f"[seed api] abandon : solde négatif pour {', '.join(negative)} (jeu de données incohérent).")
            return 1

        db.commit()
        log_event("seed_transactions", created=len(DEMO_TRANSACTIONS))
        print(f"[seed api] {created_accounts} compte(s) créé(s), {len(DEMO_TRANSACTIONS)} transactions insérées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
