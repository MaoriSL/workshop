"""
Accès à PostgreSQL via SQLAlchemy 2 (sessions synchrones, exécutées par FastAPI
dans un pool de threads). Toutes les requêtes passent par l'ORM : jamais de SQL
construit par concaténation.
"""
from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .metrics import DB_ERRORS
from .settings import settings

logger = logging.getLogger("poupal.db")


class Base(DeclarativeBase):
    """Classe de base des modèles ORM."""


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # détecte les connexions mortes (utile après un incident)
    pool_size=5,
    max_overflow=5,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dépendance FastAPI : une session par requête, toujours fermée."""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError:
        DB_ERRORS.labels(settings.service_name).inc()
        db.rollback()
        raise
    finally:
        db.close()


def check_database() -> bool:
    """Sonde de readiness : la base répond-elle à SELECT 1 ?"""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        DB_ERRORS.labels(settings.service_name).inc()
        logger.warning("database_unreachable", extra={"fields": {"event": "database_unreachable", "error": str(exc)[:200]}})
        return False
