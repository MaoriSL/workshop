"""
Point UNIQUE de lecture des secrets du service (clés JWT).

Aujourd'hui : fichiers PEM montés en lecture seule dans le conteneur (/run/secrets).
Demain : Vault ou SOPS — seule l'implémentation de ces fonctions changera.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .settings import settings


class SecretUnavailableError(RuntimeError):
    """Un secret indispensable est absent ou illisible."""


def _read_pem(path: str, label: str) -> str:
    file = Path(path)
    if not file.is_file():
        raise SecretUnavailableError(f"{label} introuvable : {path}")
    content = file.read_text(encoding="utf-8").strip()
    if "-----BEGIN" not in content:
        raise SecretUnavailableError(f"{label} invalide (format PEM attendu) : {path}")
    return content


@lru_cache(maxsize=1)
def load_jwt_private_key() -> str:
    """Clé privée RSA : signe les jetons. Service auth uniquement."""
    return _read_pem(settings.jwt_private_key_path, "Clé privée JWT")


@lru_cache(maxsize=1)
def load_jwt_public_key() -> str:
    """Clé publique RSA : vérifie les jetons (GET /auth/me)."""
    return _read_pem(settings.jwt_public_key_path, "Clé publique JWT")


def secrets_available() -> bool:
    """Sonde de readiness : les clés sont-elles chargeables ?"""
    try:
        load_jwt_private_key()
        load_jwt_public_key()
        return True
    except SecretUnavailableError:
        return False
