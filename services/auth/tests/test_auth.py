"""
Tests fonctionnels des routes /auth/* : inscription, connexion, profil.

Ils ne s'appuient que sur le CONTRAT d'API (chemins, corps, codes HTTP, codes
d'erreur `{"message", "code"}`), jamais sur l'implémentation interne des routeurs.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import jwt
import pytest

from .conftest import TEST_PASSWORD, generate_rsa_keypair

REGISTER = "/auth/register"
LOGIN = "/auth/login"
ME = "/auth/me"

INVALID_CREDENTIALS = {"message": "Email ou mot de passe incorrect.", "code": "invalid_credentials"}
AUTH_REQUIRED = {"message": "Authentification requise.", "code": "invalid_token"}


def assert_unauthenticated(response) -> None:
    """Réponse attendue pour un jeton absent / invalide / expiré sur /auth/me."""
    assert response.status_code == 401, response.text
    assert response.json() == AUTH_REQUIRED
    assert "bearer" in response.headers.get("WWW-Authenticate", "").lower()


# --------------------------------------------------------------------------- register


def test_register_returns_201_and_profile(client, user_payload):
    response = client.post(REGISTER, json=user_payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "email", "name", "created_at"}
    assert body["email"] == user_payload["email"]
    assert body["name"] == user_payload["name"]
    uuid.UUID(body["id"])  # identifiant valide
    datetime.fromisoformat(body["created_at"])  # date ISO 8601
    # Rien de sensible ne doit sortir
    assert "password" not in response.text and "password_hash" not in response.text


def test_register_stores_email_in_lowercase(client, user_payload):
    user_payload["email"] = "Alice.MAJUSCULES@Poupal.Demo"
    response = client.post(REGISTER, json=user_payload)

    assert response.status_code == 201, response.text
    assert response.json()["email"] == "alice.majuscules@poupal.demo"
    # La connexion fonctionne avec la forme normalisée
    login = client.post(LOGIN, json={"email": "alice.majuscules@poupal.demo", "password": user_payload["password"]})
    assert login.status_code == 200, login.text


def test_register_duplicate_email_returns_409(client, registered_user, user_payload):
    response = client.post(REGISTER, json=user_payload)

    assert response.status_code == 409, response.text
    assert response.json() == {"message": "Un compte existe déjà avec cet email.", "code": "email_already_used"}


def test_register_duplicate_email_is_case_insensitive(client, registered_user, user_payload):
    user_payload["email"] = registered_user["email"].upper()
    response = client.post(REGISTER, json=user_payload)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "email_already_used"


def test_register_short_password_returns_422(client, user_payload, settings):
    user_payload["password"] = "x" * (settings.password_min_length - 1)
    response = client.post(REGISTER, json=user_payload)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["message"] == "Requête invalide."
    assert body["code"] == "validation_error"
    assert any(error["field"] == "password" for error in body["errors"])


@pytest.mark.parametrize(
    "field, value",
    [
        ("name", "A"),  # trop court (2 caractères minimum)
        ("name", "x" * 81),  # trop long (80 maximum)
        ("email", "pas-un-email"),  # EmailStr
        ("email", ""),
    ],
)
def test_register_invalid_field_returns_422(client, user_payload, field, value):
    user_payload[field] = value
    response = client.post(REGISTER, json=user_payload)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "validation_error"
    assert any(error["field"] == field for error in body["errors"])


def test_register_missing_fields_returns_422(client):
    response = client.post(REGISTER, json={})

    assert response.status_code == 422, response.text
    fields = {error["field"] for error in response.json()["errors"]}
    assert {"name", "email", "password"} <= fields


# --------------------------------------------------------------------------- login


def test_login_returns_token_verifiable_with_public_key(client, registered_user, jwt_keys, settings):
    response = client.post(LOGIN, json={"email": registered_user["email"], "password": registered_user["password"]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.jwt_expires_minutes * 60

    token = body["access_token"]
    assert jwt.get_unverified_header(token)["alg"] == "RS256"
    # Même vérification que celle faite par l'API métier (clé PUBLIQUE uniquement)
    claims = jwt.decode(
        token,
        jwt_keys.public_pem,
        algorithms=["RS256"],
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub"]},
    )
    assert claims["iss"] == settings.jwt_issuer
    assert claims["sub"] == registered_user["id"]
    assert claims["email"] == registered_user["email"]
    assert claims["name"] == registered_user["name"]
    assert claims["exp"] - claims["iat"] == settings.jwt_expires_minutes * 60


def test_login_failure_is_generic(client, registered_user):
    """Email inconnu ou mauvais mot de passe : même code, même message (pas d'énumération de comptes)."""
    unknown_email = client.post(LOGIN, json={"email": "inconnu@poupal.demo", "password": TEST_PASSWORD})
    bad_password = client.post(LOGIN, json={"email": registered_user["email"], "password": "mauvais-mot-de-passe"})

    assert unknown_email.status_code == 401, unknown_email.text
    assert bad_password.status_code == 401, bad_password.text
    assert unknown_email.json() == INVALID_CREDENTIALS
    assert unknown_email.json() == bad_password.json()


def test_login_invalid_body_returns_422(client):
    response = client.post(LOGIN, json={"email": "pas-un-email"})

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


def test_login_sixth_attempt_is_rate_limited(client, registered_user, settings, reset_limiters):
    from app.core.rate_limit import parse_limit

    max_attempts, _window = parse_limit(settings.login_rate_limit)  # "5/60" → 5 essais par minute
    credentials = {"email": registered_user["email"], "password": "mauvais-mot-de-passe"}

    for attempt in range(max_attempts):
        response = client.post(LOGIN, json=credentials)
        assert response.status_code == 401, f"essai {attempt + 1} : {response.text}"

    # Essai de trop : bloqué avant même de vérifier le mot de passe
    response = client.post(LOGIN, json=credentials)
    assert response.status_code == 429, response.text
    assert response.json() == {"message": "Trop de tentatives. Réessayez dans un instant.", "code": "rate_limited"}
    assert int(response.headers["Retry-After"]) >= 1

    # La métrique métier compte le blocage
    metrics = client.get("/metrics").text
    assert 'poupal_login_attempts_total{result="rate_limited"}' in metrics

    # Une fois le limiteur remis à zéro (ce que fait la fixture entre deux tests), on peut se connecter
    reset_limiters()
    response = client.post(LOGIN, json={"email": registered_user["email"], "password": registered_user["password"]})
    assert response.status_code == 200, response.text


def test_login_attempts_are_counted_in_metrics(client, registered_user):
    client.post(LOGIN, json={"email": registered_user["email"], "password": registered_user["password"]})
    client.post(LOGIN, json={"email": registered_user["email"], "password": "mauvais-mot-de-passe"})

    metrics = client.get("/metrics").text
    assert 'poupal_login_attempts_total{result="success"}' in metrics
    assert 'poupal_login_attempts_total{result="failure"}' in metrics


# --------------------------------------------------------------------------- me


def test_me_returns_profile(client, registered_user, auth_headers):
    response = client.get(ME, headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": registered_user["id"],
        "email": registered_user["email"],
        "name": registered_user["name"],
        "created_at": registered_user["created_at"],
    }


def test_me_without_token_returns_401(client):
    assert_unauthenticated(client.get(ME))


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer pas-un-jeton",
        "Bearer aaa.bbb.ccc",
        "Bearer ",
        "Basic YWxpY2U6c2VjcmV0",  # mauvais schéma
    ],
)
def test_me_invalid_token_returns_401(client, authorization):
    assert_unauthenticated(client.get(ME, headers={"Authorization": authorization}))


def test_me_expired_token_returns_401(client, registered_user, sign_token):
    # Jeton correctement signé mais expiré depuis une minute
    token = sign_token(registered_user, iat_delta=-3600, exp_delta=-60)
    assert_unauthenticated(client.get(ME, headers={"Authorization": f"Bearer {token}"}))


def test_me_token_with_wrong_issuer_returns_401(client, registered_user, sign_token):
    token = sign_token(registered_user, issuer="autre-emetteur")
    assert_unauthenticated(client.get(ME, headers={"Authorization": f"Bearer {token}"}))


def test_me_token_signed_with_another_key_returns_401(client, registered_user, sign_token):
    # Un attaquant qui signe avec sa propre clé RSA ne doit jamais passer
    other_private_pem, _other_public_pem = generate_rsa_keypair()
    token = sign_token(registered_user, private_pem=other_private_pem)
    assert_unauthenticated(client.get(ME, headers={"Authorization": f"Bearer {token}"}))


def test_me_handmade_token_with_our_key_is_accepted(client, registered_user, sign_token):
    """Contrôle de la fixture sign_token : un jeton valide signé avec la clé de test passe."""
    token = sign_token(registered_user)
    response = client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    assert response.json()["id"] == registered_user["id"]
