"""
Primitives de sécurité du service : hachage des mots de passe (Argon2) et jetons JWT (RS256).

- Argon2id (argon2-cffi, paramètres par défaut) : lent par construction, sel aléatoire
  intégré à la chaîne produite. On ne stocke jamais un mot de passe en clair.
- JWT signés avec la clé PRIVÉE RSA (ce service uniquement) et vérifiés avec la clé
  PUBLIQUE (ici pour GET /auth/me, et dans l'API métier pour toutes ses routes).
Les clés sont lues via core/secrets.py, point unique d'accès aux secrets.
"""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .core.secrets import load_jwt_private_key, load_jwt_public_key
from .core.settings import settings

JWT_ALGORITHM = "RS256"

_hasher = PasswordHasher()

# Hash "témoin" calculé au démarrage à partir d'une valeur aléatoire. Quand l'email est
# inconnu, on vérifie quand même le mot de passe reçu contre ce hash : la réponse prend
# alors le même temps qu'avec un vrai compte (pas d'énumération d'emails par la latence).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


# ---------- Mots de passe ----------

def hash_password(password: str) -> str:
    """Hash Argon2 (sel et paramètres inclus dans la chaîne retournée)."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True si le mot de passe correspond au hash. Un hash illisible vaut un refus."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        # VerifyMismatchError (mauvais mot de passe) hérite de VerificationError
        return False


def dummy_verify(password: str) -> None:
    """Vérification factice, à temps constant, utilisée quand l'email n'existe pas."""
    verify_password(_DUMMY_HASH, password)


def password_needs_rehash(password_hash: str) -> bool:
    """True si le hash a été produit avec des paramètres plus faibles que les actuels."""
    return _hasher.check_needs_rehash(password_hash)


# ---------- Jetons JWT ----------

def create_access_token(user_id: uuid.UUID, email: str, name: str) -> tuple[str, int]:
    """
    Signe un jeton RS256 pour l'utilisateur. Retourne (jeton, durée de validité en secondes).
    Claims : sub (id utilisateur), email, name, iat, exp (= iat + jwt_expires_minutes), iss.
    """
    now = int(time.time())
    expires_in = settings.jwt_expires_minutes * 60
    claims = {
        "sub": str(user_id),
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + expires_in,
        "iss": settings.jwt_issuer,
    }
    token = jwt.encode(claims, load_jwt_private_key(), algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Vérifie signature, émetteur et expiration, puis renvoie les claims.
    Lève une sous-classe de jwt.PyJWTError si le jeton est invalide ou expiré.
    """
    return jwt.decode(
        token,
        load_jwt_public_key(),
        algorithms=[JWT_ALGORITHM],
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub"]},
    )
