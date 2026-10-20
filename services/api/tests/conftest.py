"""
Fixtures pytest de l'API métier Poupal (exécutées dans l'image "test", base poupal_test).

Principe : les tests parlent à l'application via HTTP (TestClient) exactement comme le
front ou le smoke test, avec de VRAIS jetons RS256 signés par une clé privée temporaire
générée au démarrage de la session. L'API ne connaît que la clé publique correspondante.

Pré-requis d'environnement (posés par infra/docker-compose.test.yml) :
  - DATABASE_URL            : rôle poupal_api, base poupal_test (schéma payments)
  - TEST_AUTH_DATABASE_URL  : rôle poupal_auth, base poupal_test (insertion des utilisateurs
                              de test dans auth.users, l'API ne voit que la vue auth.user_directory)
Les migrations du service auth doivent déjà être appliquées (scripts/run_tests.sh le fait).

Ordre important : l'application lit sa configuration à l'IMPORT (app.core.settings).
Tout ce qui doit la configurer (chemin de la clé publique, limite de débit) est donc posé
dans os.environ AVANT le premier `import app.main`, qui n'a lieu que dans la fixture `app`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

# Racine du service (services/api) : cwd d'alembic, où se trouvent alembic.ini et app/
SERVICE_ROOT = Path(__file__).resolve().parents[1]

# Le test de concurrence envoie 40 virements en quelques secondes : la limite de
# production (10/min par utilisateur) le bloquerait. Posée ici, avant tout import de l'app.
os.environ["TRANSACTION_RATE_LIMIT"] = "100000/60"


# ---------------------------------------------------------------------------
# Objets simples partagés par les tests
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DemoUser:
    """Un utilisateur de test, tel qu'inséré dans auth.users (jamais de vrai mot de passe)."""

    id: uuid.UUID
    email: str
    name: str


@dataclass(frozen=True)
class Users:
    """Les trois utilisateurs disponibles dans chaque test."""

    alice: DemoUser
    bob: DemoUser
    carol: DemoUser


@dataclass(frozen=True)
class JwtKeys:
    """Paire RSA temporaire : la privée signe (comme le ferait le service auth), la publique vérifie."""

    private_pem: str
    public_pem: str
    public_path: Path


class PoupalApi:
    """
    Petit client métier au-dessus de TestClient : chaque méthode correspond à une route
    du contrat (BACK-BRIEF-2.md) et renvoie la réponse HTTP brute, que le test inspecte.
    """

    def __init__(self, client: TestClient, make_token) -> None:  # type: ignore[no-untyped-def]
        self.client = client
        self.make_token = make_token

    def headers(self, user: DemoUser | None) -> dict[str, str]:
        """En-tête Authorization pour `user` (aucun en-tête si None)."""
        if user is None:
            return {}
        return {"Authorization": f"Bearer {self.make_token(user)}"}

    def me(self, user: DemoUser | None, **extra_headers: str):
        return self.client.get("/api/accounts/me", headers={**self.headers(user), **extra_headers})

    def balance(self, user: DemoUser) -> int:
        """Solde courant (en centimes) ; le compte est créé au passage s'il n'existe pas."""
        response = self.me(user)
        assert response.status_code == 200, response.text
        return response.json()["balance_cents"]

    def transfer(
        self,
        user: DemoUser,
        recipient_email: str,
        amount_cents: Any,
        *,
        key: str | None = None,
        omit_key: bool = False,
        message: str | None = None,
    ):
        """POST /api/transactions. Une clé d'idempotence unique est générée si `key` est None."""
        headers = self.headers(user)
        if not omit_key:
            headers["Idempotency-Key"] = key or str(uuid.uuid4())
        body: dict[str, Any] = {"recipient_email": recipient_email, "amount_cents": amount_cents}
        if message is not None:
            body["message"] = message
        return self.client.post("/api/transactions", json=body, headers=headers)

    def history(self, user: DemoUser | None, **params: Any):
        return self.client.get("/api/transactions", params=params, headers=self.headers(user))

    def get_transaction(self, user: DemoUser | None, transaction_id: Any):
        return self.client.get(f"/api/transactions/{transaction_id}", headers=self.headers(user))

    def consistency(self):
        """Rapport de cohérence interne : sans authentification (réseau Docker uniquement)."""
        return self.client.get("/internal/consistency")


# ---------------------------------------------------------------------------
# Session : clés, base de données, migrations, application
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def jwt_keys(tmp_path_factory: pytest.TempPathFactory) -> JwtKeys:
    """Génère une paire RSA 2048 dans un dossier temporaire et pointe l'API dessus (clé publique)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()

    keys_dir = tmp_path_factory.mktemp("jwt-keys")
    private_path = keys_dir / "jwt_private.pem"
    public_path = keys_dir / "jwt_public.pem"
    private_path.write_text(private_pem, encoding="utf-8")
    public_path.write_text(public_pem, encoding="utf-8")

    # Avant l'import de l'application : settings lira ces chemins
    os.environ["JWT_PRIVATE_KEY_PATH"] = str(private_path)
    os.environ["JWT_PUBLIC_KEY_PATH"] = str(public_path)
    return JwtKeys(private_pem=private_pem, public_pem=public_pem, public_path=public_path)


@pytest.fixture(scope="session")
def database_urls() -> tuple[str, str]:
    """(URL rôle poupal_api, URL rôle poupal_auth) ; arrêt clair si l'environnement est incomplet."""
    api_url = os.environ.get("DATABASE_URL", "").strip()
    auth_url = os.environ.get("TEST_AUTH_DATABASE_URL", "").strip()
    if not api_url or not auth_url:
        pytest.exit(
            "Tests API : DATABASE_URL et TEST_AUTH_DATABASE_URL doivent pointer sur la base poupal_test "
            "(voir infra/docker-compose.test.yml et scripts/run_tests.sh).",
            returncode=1,
        )
    return api_url, auth_url


@pytest.fixture(scope="session")
def api_engine(database_urls: tuple[str, str]):
    """Connexion de maintenance (rôle poupal_api) : TRUNCATE du schéma payments entre les tests."""
    engine = create_engine(database_urls[0], poolclass=NullPool, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def auth_engine(database_urls: tuple[str, str]):
    """Connexion de maintenance (rôle poupal_auth) : utilisateurs de test dans auth.users."""
    engine = create_engine(database_urls[1], poolclass=NullPool, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_db(auth_engine) -> None:  # type: ignore[no-untyped-def]
    """Vérifie que le schéma auth est en place puis applique les migrations de l'API (alembic)."""
    with auth_engine.connect() as connection:
        view_exists = connection.execute(text("SELECT to_regclass('auth.user_directory')")).scalar()
    if view_exists is None:
        pytest.exit(
            "La vue auth.user_directory n'existe pas : appliquez d'abord les migrations du service auth "
            "sur poupal_test (scripts/run_tests.sh s'en charge).",
            returncode=1,
        )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        pytest.exit(f"alembic upgrade head a échoué :\n{result.stdout}\n{result.stderr}", returncode=1)


@pytest.fixture(scope="session")
def app(jwt_keys: JwtKeys, migrated_db: None):
    """Importe l'application APRÈS la mise en place de l'environnement et renvoie l'objet FastAPI."""
    from app.core import secrets as secrets_module
    from app.core.settings import settings

    # Ceinture et bretelles : même si settings avait été importé plus tôt, on force le chemin
    # de la clé publique et on vide le cache de lecture du secret.
    settings.jwt_public_key_path = str(jwt_keys.public_path)
    secrets_module.load_jwt_public_key.cache_clear()

    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture(scope="session")
def api_settings(app):  # type: ignore[no-untyped-def]
    """Les réglages effectifs de l'API (solde de démo, montant maximal, émetteur JWT...)."""
    from app.core.settings import settings

    return settings


@pytest.fixture(scope="session")
def client(app):  # type: ignore[no-untyped-def]
    """Client HTTP de test ; le bloc `with` déclenche le cycle de vie de l'application."""
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Par test : base propre, limiteurs remis à zéro, utilisateurs de test, jetons
# ---------------------------------------------------------------------------
def _reset_rate_limiters() -> None:
    """Remet à zéro le limiteur de débit (en mémoire, par utilisateur) de POST /api/transactions."""
    from app.services.transfer import transaction_limiter

    transaction_limiter.reset()


@pytest.fixture(autouse=True)
def clean_db(app, api_engine, auth_engine) -> None:  # type: ignore[no-untyped-def]
    """Avant chaque test : tables payments.* et auth.users vidées, limiteurs remis à zéro."""
    with api_engine.begin() as connection:
        # lock_timeout : si une session applicative a été oubliée ouverte, on échoue vite et clairement
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("TRUNCATE TABLE payments.idempotency_keys, payments.transactions, payments.accounts"))
    with auth_engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("TRUNCATE TABLE auth.users"))
    _reset_rate_limiters()


@pytest.fixture
def users(clean_db: None, auth_engine) -> Users:  # type: ignore[no-untyped-def]
    """Insère trois utilisateurs dans auth.users (hash de mot de passe factice : jamais de login ici)."""
    created = []
    with auth_engine.begin() as connection:
        for name, email in (
            ("Alice Martin", "alice@poupal.demo"),
            ("Bob Dupont", "bob@poupal.demo"),
            ("Carol Bernard", "carol@poupal.demo"),
        ):
            user = DemoUser(id=uuid.uuid4(), email=email, name=name)
            connection.execute(
                text(
                    "INSERT INTO auth.users (id, email, name, password_hash) "
                    "VALUES (:id, :email, :name, :password_hash)"
                ),
                {"id": user.id, "email": user.email, "name": user.name, "password_hash": "x"},
            )
            created.append(user)
    return Users(alice=created[0], bob=created[1], carol=created[2])


@pytest.fixture
def make_token(jwt_keys: JwtKeys, api_settings):  # type: ignore[no-untyped-def]
    """
    Fabrique de jetons : signe comme le service auth (RS256, mêmes claims).
    `expires_in` négatif → jeton expiré ; `issuer` / `private_pem` permettent de forger un jeton invalide.
    """

    def _make_token(
        user: DemoUser,
        *,
        expires_in: int = 1800,
        issuer: str | None = None,
        private_pem: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "iat": now - timedelta(seconds=60),  # une minute dans le passé : insensible aux horloges
            "exp": now + timedelta(seconds=expires_in),
            "iss": issuer if issuer is not None else api_settings.jwt_issuer,
        }
        return jwt.encode(claims, private_pem or jwt_keys.private_pem, algorithm="RS256")

    return _make_token


@pytest.fixture
def pay(client: TestClient, make_token) -> PoupalApi:  # type: ignore[no-untyped-def]
    """Le client métier utilisé par la plupart des tests."""
    return PoupalApi(client, make_token)
