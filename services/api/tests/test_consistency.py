"""
GET /internal/consistency : rapport de cohérence du grand livre, lu par la supervision et le
moteur de remédiation (preuve que la reprise n'a pas corrompu les soldes). Sans authentification
(la gateway bloque /internal/ depuis l'extérieur) et toujours 200 : c'est un rapport, pas une sonde.
"""
from __future__ import annotations

from datetime import datetime


def _assert_report_ok(body: dict, expected_accounts_sum: int) -> None:  # type: ignore[type-arg]
    assert body["status"] == "ok"
    checks = body["checks"]
    assert checks["negative_balances"] == {"ok": True, "count": 0}
    assert checks["total_conservation"]["ok"] is True
    assert checks["total_conservation"]["sum_balances_cents"] == expected_accounts_sum
    assert checks["total_conservation"]["sum_opening_balances_cents"] == expected_accounts_sum
    assert checks["per_account_ledger"] == {"ok": True, "mismatches": []}
    datetime.fromisoformat(body["checked_at"])


def test_consistency_on_empty_ledger(pay):
    response = pay.consistency()

    assert response.status_code == 200, response.text
    _assert_report_ok(response.json(), expected_accounts_sum=0)


def test_consistency_after_several_transfers(pay, users, api_settings):
    """Virements réussis, un refus pour solde insuffisant : la somme des soldes est conservée."""
    initial = api_settings.demo_initial_balance_cents

    assert pay.transfer(users.alice, users.bob.email, 25000).status_code == 201
    assert pay.transfer(users.bob, users.carol.email, 12000).status_code == 201
    assert pay.transfer(users.carol, users.alice.email, 7000).status_code == 201
    assert pay.transfer(users.alice, users.carol.email, 300).status_code == 201
    refused = pay.transfer(users.bob, users.alice.email, initial + 25000)  # > solde de Bob
    assert refused.status_code == 422 and refused.json()["code"] == "insufficient_funds"

    response = pay.consistency()

    assert response.status_code == 200, response.text
    _assert_report_ok(response.json(), expected_accounts_sum=3 * initial)

    # Le ledger de chaque compte correspond bien aux soldes renvoyés par l'API
    assert pay.balance(users.alice) == initial - 25000 + 7000 - 300
    assert pay.balance(users.bob) == initial + 25000 - 12000
    assert pay.balance(users.carol) == initial + 12000 - 7000 + 300


def test_consistency_does_not_require_a_token(client):
    response = client.get("/internal/consistency")

    assert response.status_code == 200
    assert "checks" in response.json()
