"""
Virements concurrents : 40 requêtes entrelacées A→B et B→A envoyées par 8 threads.
Ce que l'on prouve : le verrouillage des deux comptes (SELECT ... FOR UPDATE dans un ordre
constant) évite toute course et tout interblocage — l'argent n'est ni créé ni perdu,
aucun solde ne devient négatif, et l'API ne renvoie jamais de 5xx.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

WORKERS = 8
TRANSFERS = 40


def test_interleaved_transfers_preserve_the_total(pay, users, api_settings):
    initial = api_settings.demo_initial_balance_cents
    alice, bob = users.alice, users.bob

    # Comptes créés à l'avance : le test porte sur les virements, pas sur la création
    assert pay.balance(alice) == initial
    assert pay.balance(bob) == initial

    # Montants variés et déterministes (de 5,00 € à 44,99 €), sens alterné à chaque virement
    plan = []
    for i in range(TRANSFERS):
        sender, recipient = (alice, bob) if i % 2 == 0 else (bob, alice)
        plan.append((sender, recipient, 500 + (i * 137) % 4000))

    def run_transfer(index: int) -> tuple[int, dict]:  # type: ignore[type-arg]
        sender, recipient, amount = plan[index]
        try:
            response = pay.transfer(sender, recipient.email, amount, message=f"Virement concurrent {index}")
            return response.status_code, response.json()
        except Exception as exc:  # une exception levée côté serveur compte comme un 5xx
            return 500, {"message": repr(exc), "code": "exception"}

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        results = list(executor.map(run_transfer, range(TRANSFERS)))

    # 1. Aucune erreur serveur, uniquement 201 ou 422 insufficient_funds
    server_errors = [(status, body) for status, body in results if status >= 500]
    assert not server_errors, f"réponses 5xx : {server_errors}"
    for status, body in results:
        assert status in (201, 422), (status, body)
        if status == 422:
            assert body["code"] == "insufficient_funds", body

    # 2. Les soldes finaux sont exactement ceux déduits des virements acceptés
    expected = {alice.id: initial, bob.id: initial}
    completed = 0
    for (sender, recipient, amount), (status, _) in zip(plan, results):
        if status == 201:
            expected[sender.id] -= amount
            expected[recipient.id] += amount
            completed += 1
    final_alice, final_bob = pay.balance(alice), pay.balance(bob)
    assert final_alice == expected[alice.id]
    assert final_bob == expected[bob.id]

    # 3. Conservation de la somme et aucun solde négatif
    assert final_alice + final_bob == 2 * initial
    assert final_alice >= 0 and final_bob >= 0

    # 4. Chaque tentative est tracée (completed ou failed) et le grand livre est cohérent
    history = pay.history(alice, limit=100).json()
    assert history["total"] == TRANSFERS
    assert sum(1 for item in history["items"] if item["status"] == "completed") == completed

    report = pay.consistency().json()
    assert report["status"] == "ok", report
    assert report["checks"]["per_account_ledger"]["mismatches"] == []
