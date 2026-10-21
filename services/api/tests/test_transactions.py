"""
POST /api/transactions, GET /api/transactions, GET /api/transactions/{id} :
virement nominal, règles métier (solde, auto-envoi, montants, destinataire), détail et pagination.
Les montants sont des entiers en centimes.
"""
from __future__ import annotations

import re
import uuid

import pytest

REFERENCE_PATTERN = re.compile(r"^PP-\d{4}-\d{6}$")


# ---------------------------------------------------------------------------
# Virement nominal
# ---------------------------------------------------------------------------
def test_transfer_updates_both_balances(pay, users, api_settings):
    initial = api_settings.demo_initial_balance_cents

    response = pay.transfer(users.alice, users.bob.email, 2500, message="Resto de vendredi")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["type"] == "sent"
    assert body["amount_cents"] == 2500
    assert body["currency"] == api_settings.currency
    assert body["message"] == "Resto de vendredi"
    assert body["failure_reason"] is None
    assert REFERENCE_PATTERN.match(body["reference"]), body["reference"]
    assert body["counterparty"] == {"user_id": str(users.bob.id), "email": users.bob.email, "name": users.bob.name}

    # Débit chez l'émetteur, crédit chez le destinataire (dont le compte a été créé au passage)
    assert pay.balance(users.alice) == initial - 2500
    assert pay.balance(users.bob) == initial + 2500


def test_transfer_appears_in_both_histories_with_relative_type(pay, users):
    transaction_id = pay.transfer(users.alice, users.bob.email, 1000).json()["id"]

    sent = pay.history(users.alice).json()
    received = pay.history(users.bob).json()

    assert sent["total"] == 1 and sent["items"][0]["id"] == transaction_id
    assert sent["items"][0]["type"] == "sent"
    assert sent["items"][0]["counterparty"]["email"] == users.bob.email

    assert received["total"] == 1 and received["items"][0]["id"] == transaction_id
    assert received["items"][0]["type"] == "received"
    assert received["items"][0]["counterparty"]["email"] == users.alice.email


def test_transfer_detail_is_visible_to_sender_and_recipient(pay, users):
    created = pay.transfer(users.alice, users.bob.email, 1000).json()

    as_sender = pay.get_transaction(users.alice, created["id"])
    as_recipient = pay.get_transaction(users.bob, created["id"])

    assert as_sender.status_code == 200, as_sender.text
    assert as_sender.json() == created  # même TransactionOut que la réponse de création
    assert as_recipient.status_code == 200
    assert as_recipient.json()["type"] == "received"
    assert as_recipient.json()["counterparty"]["email"] == users.alice.email


def test_recipient_email_is_case_insensitive(pay, users):
    """L'annuaire stocke les emails en minuscules : la recherche doit l'être aussi."""
    response = pay.transfer(users.alice, users.bob.email.upper(), 500)

    assert response.status_code == 201, response.text
    assert response.json()["counterparty"]["email"] == users.bob.email


def test_references_are_unique_and_increasing(pay, users):
    first = pay.transfer(users.alice, users.bob.email, 100).json()["reference"]
    second = pay.transfer(users.alice, users.bob.email, 100).json()["reference"]

    assert first != second
    assert int(second.split("-")[-1]) > int(first.split("-")[-1])


# ---------------------------------------------------------------------------
# Règles métier
# ---------------------------------------------------------------------------
def test_insufficient_funds_records_a_failed_transaction(pay, users, api_settings):
    initial = api_settings.demo_initial_balance_cents
    amount = initial + 1
    assert amount <= api_settings.max_transaction_cents, "le test suppose solde démo < montant maximal"

    response = pay.transfer(users.alice, users.bob.email, amount)

    assert response.status_code == 422, response.text
    assert response.json() == {"message": "Solde insuffisant.", "code": "insufficient_funds"}

    # Aucun mouvement d'argent...
    assert pay.balance(users.alice) == initial
    assert pay.balance(users.bob) == initial

    # ... mais la tentative est tracée dans l'historique de l'émetteur
    history = pay.history(users.alice).json()
    assert history["total"] == 1
    failed = history["items"][0]
    assert failed["status"] == "failed"
    assert failed["failure_reason"] == "insufficient_funds"
    assert failed["type"] == "sent"
    assert failed["amount_cents"] == amount


def test_self_transfer_is_rejected(pay, users, api_settings):
    response = pay.transfer(users.alice, users.alice.email, 100)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "self_transfer"
    assert pay.balance(users.alice) == api_settings.demo_initial_balance_cents
    assert pay.history(users.alice).json()["total"] == 0


@pytest.mark.parametrize("amount", [0, -1, -5000])
def test_non_positive_amount_is_rejected(pay, users, amount):
    response = pay.transfer(users.alice, users.bob.email, amount)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert any(error["field"] == "amount_cents" for error in response.json()["errors"])


def test_amount_above_maximum_is_rejected(pay, users, api_settings):
    response = pay.transfer(users.alice, users.bob.email, api_settings.max_transaction_cents + 1)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "amount_too_large"
    assert pay.history(users.alice).json()["total"] == 0


def test_unknown_recipient_is_rejected(pay, users, api_settings):
    response = pay.transfer(users.alice, "inconnu@poupal.demo", 100)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "recipient_not_found"
    assert pay.balance(users.alice) == api_settings.demo_initial_balance_cents
    assert pay.history(users.alice).json()["total"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {"recipient_email": "pas-un-email", "amount_cents": 100},
        {"recipient_email": "bob@poupal.demo", "amount_cents": "cent"},
        {"recipient_email": "bob@poupal.demo", "amount_cents": 10.5},
        {"recipient_email": "bob@poupal.demo"},
        {"recipient_email": "bob@poupal.demo", "amount_cents": 100, "message": "x" * 141},
    ],
)
def test_invalid_body_is_rejected_by_validation(client, make_token, users, body):
    response = client.post(
        "/api/transactions",
        json=body,
        headers={"Authorization": f"Bearer {make_token(users.alice)}", "Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert response.json()["message"] == "Requête invalide."


# ---------------------------------------------------------------------------
# Détail : jamais 403, toujours 404 pour ce qui n'appartient pas à l'utilisateur
# ---------------------------------------------------------------------------
def test_third_party_cannot_see_a_transaction(pay, users):
    transaction_id = pay.transfer(users.alice, users.bob.email, 1000).json()["id"]

    response = pay.get_transaction(users.carol, transaction_id)

    assert response.status_code == 404, response.text
    assert response.json() == {"message": "Transaction introuvable.", "code": "transaction_not_found"}


def test_unknown_or_malformed_transaction_id_returns_404(pay, users):
    assert pay.get_transaction(users.alice, uuid.uuid4()).status_code == 404
    malformed = pay.get_transaction(users.alice, "pas-un-uuid")
    assert malformed.status_code == 404
    assert malformed.json()["code"] == "transaction_not_found"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
def test_history_is_paginated_most_recent_first(pay, users):
    ids = [pay.transfer(users.alice, users.bob.email, 100 + i).json()["id"] for i in range(5)]

    page1 = pay.history(users.alice, limit=2, offset=0).json()
    page2 = pay.history(users.alice, limit=2, offset=2).json()
    page3 = pay.history(users.alice, limit=2, offset=4).json()
    beyond = pay.history(users.alice, limit=2, offset=10).json()

    assert (page1["total"], page1["limit"], page1["offset"]) == (5, 2, 0)
    assert len(page1["items"]) == 2 and len(page2["items"]) == 2 and len(page3["items"]) == 1
    assert beyond["items"] == [] and beyond["total"] == 5

    # Tri par date décroissante : la dernière créée en premier, pas de doublon entre les pages
    assert page1["items"][0]["id"] == ids[-1]
    seen = [item["id"] for item in page1["items"] + page2["items"] + page3["items"]]
    assert sorted(seen) == sorted(ids)
    dates = [item["created_at"] for item in page1["items"] + page2["items"] + page3["items"]]
    assert dates == sorted(dates, reverse=True)

    # Le destinataire voit les mêmes transactions, en "received"
    received = pay.history(users.bob, limit=100).json()
    assert received["total"] == 5
    assert {item["type"] for item in received["items"]} == {"received"}


def test_history_default_page_size(pay, users):
    response = pay.history(users.alice).json()
    assert (response["limit"], response["offset"]) == (20, 0)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "dix"}])
def test_invalid_pagination_parameters_are_rejected(pay, users, params):
    response = pay.history(users.alice, **params)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
