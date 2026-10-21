"""
Données de démonstration du service auth : les 10 utilisateurs fictifs de Poupal.

Lancement : `python -m app.seed` (fait automatiquement par entrypoint.sh si SEED_DEMO_DATA=true).
Idempotent : un utilisateur déjà présent n'est ni recréé ni modifié, le script peut donc
être relancé à chaque démarrage. Le mot de passe commun vient de DEMO_PASSWORD (jamais du code).
Les comptes et transactions associés sont créés par le seed de l'API métier (services/api).
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.database import SessionLocal
from .core.logging import configure_logging, log_event
from .core.settings import settings
from .models import User
from .security import hash_password

# (email, nom affiché) — domaine .demo : adresses volontairement fictives
DEMO_USERS: list[tuple[str, str]] = [
    ("alex@poupal.demo", "Alex Martin"),
    ("camille@poupal.demo", "Camille Dupont"),
    ("lea@poupal.demo", "Léa Bernard"),
    ("nathan@poupal.demo", "Nathan Petit"),
    ("julie@poupal.demo", "Julie Moreau"),
    ("hugo@poupal.demo", "Hugo Garnier"),
    # Ajoutés pour le générateur de trafic (10 utilisateurs simulés au maximum)
    ("sophie@poupal.demo", "Sophie Lambert"),
    ("lucas@poupal.demo", "Lucas Fontaine"),
    ("emma@poupal.demo", "Emma Lefèvre"),
    ("thomas@poupal.demo", "Thomas Roux"),
]


def seed_users(db: Session, password: str) -> int:
    """Crée les utilisateurs manquants avec le mot de passe donné. Retourne le nombre créés."""
    emails = [email for email, _ in DEMO_USERS]
    existing = set(db.scalars(select(User.email).where(User.email.in_(emails))))

    created = 0
    for email, name in DEMO_USERS:
        if email in existing:
            continue
        # Un hash par utilisateur : sels distincts, donc hashs distincts malgré le mot de passe commun
        db.add(User(email=email, name=name, password_hash=hash_password(password)))
        created += 1
    db.commit()
    return created


def main() -> int:
    configure_logging(settings.service_name, settings.log_level)

    password = settings.demo_password
    if not password:
        print("[auth] seed impossible : la variable DEMO_PASSWORD est absente ou vide.", file=sys.stderr)
        log_event("seed_users_failed", logging.ERROR, reason="demo_password_missing")
        return 1
    if len(password) < settings.password_min_length:
        # On n'empêche pas la démo, mais on prévient : /auth/register refuserait ce mot de passe
        log_event("seed_users_warning", logging.WARNING, reason="demo_password_shorter_than_min_length")

    with SessionLocal() as db:
        created = seed_users(db, password)

    log_event("seed_users", created=created, total=len(DEMO_USERS))
    print(f"[auth] seed terminé : {created} utilisateur(s) créé(s), {len(DEMO_USERS) - created} déjà présent(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
