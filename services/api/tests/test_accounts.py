"""
GET /api/accounts/me : création automatique du compte, idempotence, et vérification du jeton
(toutes les routes /api/* exigent un Bearer RS256 valide, sinon 401 invalid_token).
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from .conftest import DemoUser


def test_account_is_created_with_demo_balance(pay, users, api_settings):
    """Premier appel : le compte n'existe pas encore, il est créé avec le solde de démonstration."""
    response = pay.me(users.alice)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == str(users.alice.id)
    assert body["balance_cents"] == api_settings.demo_initial_balance_cents
    assert body["opening_balance_cents"] == api_settings.demo_initial_balance_cents
    assert body["currency"] == api_settings.currency
    uuid.UUID(body["account_id"])  # identifiant bien formé
    datetime.fromisoformat(body["created_at"])  # date ISO 8601


def test_account_creation_is_idempotent(pay, users):
    """Deux appels renvoient le même compte (aucun doublon, solde inchangé)."""
    first = pay.me(users.alice).json()
    second = pay.me(users.alice).json()

    assert second["account_id"] == first["account_id"]
    assert second["balance_cents"] == first["balance_cents"]
    assert second["created_at"] == first["created_at"]


def test_each_user_gets_their_own_account(pay, users):
    alice = pay.me(users.alice).json()
    bob = pay.me(users.bob).json()

    assert alice["account_id"] != bob["account_id"]
    assert alice["user_id"] == str(users.alice.id)
    assert bob["user_id"] == str(users.bob.id)


def test_history_is_empty_for_a_new_user(pay, users):
    """Un utilisateur sans compte peut consulter son historique : liste vide, pas d'erreur."""
    response = pay.history(users.carol)

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_request_id_is_returned(pay, users):
    """Le middleware propage X-Request-ID (corrélation front ↔ logs ↔ SIEM)."""
    response = pay.me(users.alice, **{"X-Request-ID": "test-request-42"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-42"


# ---------------------------------------------------------------------------
# Authentification : 401 invalid_token dans tous les cas de jeton absent / invalide / expiré
# ---------------------------------------------------------------------------
def _assert_unauthorized(response) -> None:  # type: ignore[no-untyped-def]
    assert response.status_code == 401, response.text
    assert response.json() == {"message": "Authentification requise.", "code": "invalid_token"}
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_missing_token_is_rejected(pay):
    _assert_unauthorized(pay.me(None))
    _assert_unauthorized(pay.history(None))
    _assert_unauthorized(pay.get_transaction(None, uuid.uuid4()))


@pytest.mark.parametrize("authorization", ["Bearer", "Bearer pas-un-jwt", "Basic abc", "Token xyz"])
def test_malformed_authorization_header_is_rejected(client, authorization):
    response = client.get("/api/accounts/me", headers={"Authorization": authorization})
    _assert_unauthorized(response)


def test_expired_token_is_rejected(client, make_token, users):
    token = make_token(users.alice, expires_in=-120)  # exp dans le passé
    response = client.get("/api/accounts/me", headers={"Authorization": f"Bearer {token}"})
    _assert_unauthorized(response)


def test_wrong_issuer_is_rejected(client, make_token, users):
    token = make_token(users.alice, issuer="autre-emetteur")
    response = client.get("/api/accounts/me", headers={"Authorization": f"Bearer {token}"})
    _assert_unauthorized(response)


def test_token_signed_with_another_key_is_rejected(client, make_token, users):
    """Un jeton signé par une clé inconnue de l'API (attaquant) doit être refusé."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()

    token = make_token(users.alice, private_pem=other_pem)
    response = client.get("/api/accounts/me", headers={"Authorization": f"Bearer {token}"})
    _assert_unauthorized(response)


def test_valid_token_for_unknown_user_still_gets_an_account(pay):
    """
    L'API ne consulte pas auth.users pour authentifier : un jeton valide suffit (claims).
    Le compte est donc créé même si l'annuaire ne connaît pas (encore) l'utilisateur.
    """
    ghost = DemoUser(id=uuid.uuid4(), email="ghost@poupal.demo", name="Fantôme")
    response = pay.me(ghost)

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == str(ghost.id)
