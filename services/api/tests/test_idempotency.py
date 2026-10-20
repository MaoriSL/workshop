"""
En-tête Idempotency-Key sur POST /api/transactions : un client qui rejoue une requête
(timeout réseau, double clic) ne doit jamais provoquer un second virement.
"""
from __future__ import annotations

import uuid


def test_missing_idempotency_key_is_rejected(pay, users, api_settings):
    response = pay.transfer(users.alice, users.bob.email, 100, omit_key=True)

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "idempotency_key_required"
    assert pay.balance(users.alice) == api_settings.demo_initial_balance_cents
    assert pay.history(users.alice).json()["total"] == 0


def test_replay_returns_the_same_transaction_without_moving_money(pay, users, api_settings):
    initial = api_settings.demo_initial_balance_cents
    key = str(uuid.uuid4())

    first = pay.transfer(users.alice, users.bob.email, 3000, key=key, message="Loyer")
    second = pay.transfer(users.alice, users.bob.email, 3000, key=key, message="Loyer")

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json() == first.json()  # même TransactionOut (id, référence, date...)

    # Une seule transaction, un seul débit
    assert pay.history(users.alice).json()["total"] == 1
    assert pay.balance(users.alice) == initial - 3000
    assert pay.balance(users.bob) == initial + 3000


def test_same_key_with_a_different_body_is_rejected(pay, users, api_settings):
    initial = api_settings.demo_initial_balance_cents
    key = str(uuid.uuid4())

    first = pay.transfer(users.alice, users.bob.email, 3000, key=key)
    changed_amount = pay.transfer(users.alice, users.bob.email, 3001, key=key)
    changed_recipient = pay.transfer(users.alice, users.carol.email, 3000, key=key)
    changed_message = pay.transfer(users.alice, users.bob.email, 3000, key=key, message="autre")

    assert first.status_code == 201, first.text
    for response in (changed_amount, changed_recipient, changed_message):
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "idempotency_key_reused"

    assert pay.history(users.alice).json()["total"] == 1
    assert pay.balance(users.alice) == initial - 3000


def test_failed_transfer_is_replayed_as_the_same_failure(pay, users, api_settings):
    """Un échec (solde insuffisant) est lui aussi mémorisé : rejouer la clé ne crée pas de 2e échec."""
    amount = api_settings.demo_initial_balance_cents + 1
    key = str(uuid.uuid4())

    first = pay.transfer(users.alice, users.bob.email, amount, key=key)
    replay = pay.transfer(users.alice, users.bob.email, amount, key=key)

    assert first.status_code == 422 and first.json()["code"] == "insufficient_funds"
    assert replay.status_code == 422, replay.text
    assert replay.json() == first.json()
    assert pay.history(users.alice).json()["total"] == 1  # une seule transaction failed


def test_keys_are_scoped_per_user(pay, users, api_settings):
    """La même clé utilisée par deux utilisateurs différents correspond à deux requêtes distinctes."""
    key = "cle-partagee-" + str(uuid.uuid4())

    from_alice = pay.transfer(users.alice, users.carol.email, 1000, key=key)
    from_bob = pay.transfer(users.bob, users.carol.email, 1000, key=key)

    assert from_alice.status_code == 201, from_alice.text
    assert from_bob.status_code == 201, from_bob.text
    assert from_alice.json()["id"] != from_bob.json()["id"]
    assert pay.balance(users.carol) == api_settings.demo_initial_balance_cents + 2000


def test_different_keys_create_different_transactions(pay, users):
    first = pay.transfer(users.alice, users.bob.email, 1000, key="cle-1")
    second = pay.transfer(users.alice, users.bob.email, 1000, key="cle-2")

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert pay.history(users.alice).json()["total"] == 2
