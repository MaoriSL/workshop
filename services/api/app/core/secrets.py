"""
Point UNIQUE de lecture des secrets du service.

L'API ne détient que la clé PUBLIQUE JWT : elle peut vérifier les jetons émis par
le service auth mais jamais en fabriquer. Aujourd'hui : fichier PEM monté en lecture
seule (/run/secrets). Demain : Vault ou SOPS — seule cette implémentation changera.
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
def load_jwt_public_key() -> str:
    """Clé publique RSA : vérifie la signature des jetons."""
    return _read_pem(settings.jwt_public_key_path, "Clé publique JWT")


def secrets_available() -> bool:
    """Sonde de readiness : la clé publique est-elle chargeable ?"""
    try:
        load_jwt_public_key()
        return True
    except SecretUnavailableError:
        return False
