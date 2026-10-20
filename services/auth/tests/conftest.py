"""
Fixtures pytest du service d'authentification Poupal.

Principe : les tests tournent contre une VRAIE base PostgreSQL (poupal_test, voir
infra/docker-compose.test.yml) avec des clés RSA temporaires générées à la volée.
Rien n'est importé depuis `app` au moment de la collecte : la base n'est touchée
que par les fixtures (session : migrations Alembic ; fonction : TRUNCATE auth.users
+ remise à zéro du limiteur de connexions).

Variable d'environnement attendue : DATABASE_URL (rôle poupal_auth sur la base de
test). Par sécurité, le nom de la base doit contenir "test" (POUPAL_TEST_ALLOW_ANY_DB=1
pour forcer).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.engine import make_url

# Racine du service (services/auth) : cwd d'Alembic, et dossier qui contient `app/`
SERVICE_ROOT = Path(__file__).resolve().parents[1]

# Mot de passe de test (fictif, ≥ 10 caractères = settings.password_min_length)
TEST_PASSWORD = "MotDePasseDeTest-2026"


@dataclass(frozen=True)
class JwtKeys:
    """Paire RSA temporaire : la privée signe (service auth), la publique vérifie."""

    private_pem: str
    public_pem: str
    private_path: Path
    public_path: Path


def generate_rsa_keypair() -> tuple[str, str]:
    """Génère une paire RSA 2048 bits au format PEM (équivalent de scripts/gen_keys.sh)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


# --------------------------------------------------------------------------- session


@pytest.fixture(scope="session")
def jwt_keys(tmp_path_factory: pytest.TempPathFactory) -> JwtKeys:
    """Écrit des clés RSA temporaires et pointe JWT_*_KEY_PATH dessus AVANT l'import de app.main."""
    key_dir = tmp_path_factory.mktemp("jwt")
    private_pem, public_pem = generate_rsa_keypair()
    private_path = key_dir / "jwt_private.pem"
    public_path = key_dir / "jwt_public.pem"
    private_path.write_text(private_pem, encoding="utf-8")
    public_path.write_text(public_pem, encoding="utf-8")

    patch = pytest.MonkeyPatch()
    patch.setenv("JWT_PRIVATE_KEY_PATH", str(private_path))
    patch.setenv("JWT_PUBLIC_KEY_PATH", str(public_path))
    yield JwtKeys(private_pem, public_pem, private_path, public_path)
    patch.undo()


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL de la base de test, avec un garde-fou : on ne TRUNCATE jamais une base de prod/dev."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.fail("DATABASE_URL manquante : les tests ont besoin de la base poupal_test (voir scripts/run_tests.sh).")
    db_name = make_url(url).database or ""
    if "test" not in db_name and os.environ.get("POUPAL_TEST_ALLOW_ANY_DB") != "1":
        pytest.fail(f"Refus : la base « {db_name} » n'est pas une base de test (les tests vident auth.users).")
    return url


@pytest.fixture(scope="session")
def migrated_database(database_url: str, jwt_keys: JwtKeys) -> str:
    """Applique les migrations (alembic upgrade head) dans un sous-processus, cwd = racine du service."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head a échoué (base de test joignable ?)\n"
            f"--- stdout ---\n{result.stdout[-2000:]}\n--- stderr ---\n{result.stderr[-2000:]}"
        )
    return database_url


@pytest.fixture(scope="session")
def app(jwt_keys: JwtKeys, migrated_database: str):
    """Importe l'application FastAPI une fois les clés et la base prêtes."""
    from app.core import secrets
    from app.core.settings import settings as app_settings
    from app.main import app as fastapi_app

    # Ceinture et bretelles : même si `settings` avait été importé plus tôt,
    # on force les chemins des clés et on vide les caches lru de lecture.
    app_settings.jwt_private_key_path = str(jwt_keys.private_path)
    app_settings.jwt_public_key_path = str(jwt_keys.public_path)
    secrets.load_jwt_private_key.cache_clear()
    secrets.load_jwt_public_key.cache_clear()
    return fastapi_app


@pytest.fixture(scope="session")
def settings(app):
    """Objet `settings` du service (issuer, durée des jetons, limite de connexions...)."""
    from app.core.settings import settings as app_settings

    return app_settings


# --------------------------------------------------------------------------- fonction


def truncate_users() -> None:
    """Vide la table des utilisateurs (TRUNCATE : plus rapide qu'un DELETE, remet tout à plat)."""
    from app.core.database import engine

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE auth.users"))


def reset_rate_limiters() -> None:
    """Remet à zéro tous les RateLimiter exposés par les modules du service.

    Le limiteur de /auth/login (`login_limiter` dans app/routers/auth.py) est en
    mémoire et clé par IP ; sous TestClient tous les tests partagent l'IP "testclient",
    il faut donc l'oublier entre deux tests. On cherche les instances par type plutôt
    que par nom : un renommage dans le routeur ne casse pas les tests.
    """
    from app.core.rate_limit import RateLimiter

    for module_name in ("app.routers.auth", "app.security", "app.deps", "app.core.rate_limit"):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for value in vars(module).values():
            if isinstance(value, RateLimiter):
                value.reset()


@pytest.fixture(autouse=True)
def clean_state(app) -> None:
    """Avant chaque test : table users vide et limiteur de connexions remis à zéro."""
    truncate_users()
    reset_rate_limiters()


@pytest.fixture
def reset_limiters() -> Callable[[], None]:
    """Expose la remise à zéro du limiteur aux tests qui en ont besoin en cours de route."""
    return reset_rate_limiters


@pytest.fixture
def client(app, clean_state):
    """Client HTTP de test (requêtes synchrones, pas de serveur réseau)."""
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_payload() -> dict[str, str]:
    """Corps d'inscription d'un utilisateur de test (données fictives)."""
    return {"name": "Alice Test", "email": "alice.test@poupal.demo", "password": TEST_PASSWORD}


@pytest.fixture
def registered_user(client, user_payload: dict[str, str]) -> dict[str, Any]:
    """Utilisateur inscrit via POST /auth/register : corps envoyé + réponse (id, created_at...)."""
    response = client.post("/auth/register", json=user_payload)
    assert response.status_code == 201, response.text
    return {**user_payload, **response.json()}


@pytest.fixture
def access_token(client, registered_user: dict[str, Any]) -> str:
    """Jeton obtenu par un login réussi de l'utilisateur de test."""
    response = client.post("/auth/login", json={"email": registered_user["email"], "password": registered_user["password"]})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(access_token: str) -> dict[str, str]:
    """En-tête Authorization prêt à l'emploi."""
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def sign_token(jwt_keys: JwtKeys, settings) -> Callable[..., str]:
    """Fabrique de jetons signés « à la main » pour les cas limites (expiré, mauvais émetteur, autre clé).

    Exemple : sign_token(user, exp_delta=-60) → jeton expiré depuis une minute.
    """

    def _sign(
        user: dict[str, Any],
        *,
        iat_delta: int = 0,
        exp_delta: int = 60,
        issuer: str | None = None,
        private_pem: str | None = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": str(user["id"]),
            "email": user["email"],
            "name": user["name"],
            "iat": now + iat_delta,
            "exp": now + exp_delta,
            "iss": issuer if issuer is not None else settings.jwt_issuer,
        }
        return jwt.encode(claims, private_pem or jwt_keys.private_pem, algorithm="RS256")

    return _sign
