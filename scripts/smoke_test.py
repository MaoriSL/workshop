#!/usr/bin/env python3
"""
Smoke test Poupal : prouve, de bout en bout, que la plateforme fonctionne.

    1. connexion d'un compte de démo          (POST /auth/login)
    2. lecture du solde                       (GET  /api/accounts/me)
    3. envoi de 1,00 € à un autre compte      (POST /api/transactions + Idempotency-Key)
    4. la transaction est "completed"         (GET  /api/transactions/{id})
    5. le solde a baissé d'exactement 1,00 €  (GET  /api/accounts/me)
    6. cohérence des soldes, si accessible    (GET  /internal/consistency, réseau Docker)

Sortie : une ligne OK / KO par étape, puis "SMOKE OK" (code 0) ou "SMOKE KO" (code 1).
Réutilisé par le moteur de remédiation pour prouver qu'un service est rétabli.
Bibliothèque standard uniquement : utilisable partout, sans installation.
Le mot de passe et le jeton ne sont jamais affichés.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid


class StepFailed(Exception):
    """Une étape du parcours a échoué (message lisible)."""


def call(method: str, url: str, body: dict | None = None, token: str | None = None,
         headers: dict[str, str] | None = None, timeout: float = 5.0) -> tuple[int, dict]:
    """Requête JSON ; renvoie (code HTTP, corps décodé ou {})."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    request.add_header("X-Request-ID", f"smoke-{uuid.uuid4()}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _decode(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _decode(error.read())
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise StepFailed(f"{method} {url} injoignable ({error})") from error


def _decode(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode() or "{}")
    except json.JSONDecodeError:
        return {}


RESULT: dict = {"ok": False, "steps": [], "transaction": None, "balance_before_cents": None, "balance_after_cents": None, "consistency": None}


def run(args: argparse.Namespace) -> bool:
    base = args.base_url.rstrip("/")
    amount_cents = 100
    ok = True

    def report(step: int, label: str, success: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and success
        RESULT["steps"].append({"step": step, "label": label, "ok": success, "detail": detail})
        if not args.json:
            print(f"{'OK ' if success else 'KO '} étape {step} — {label}{(' : ' + detail) if detail else ''}")

    try:
        # 1. Connexion
        status, body = call("POST", f"{base}/auth/login", {"email": args.email, "password": args.password}, timeout=args.timeout)
        if status != 200 or "access_token" not in body:
            raise StepFailed(f"login refusé (HTTP {status}, {body.get('message', 'sans message')})")
        token = body["access_token"]
        report(1, "connexion", True, args.email)

        # 2. Solde initial
        status, body = call("GET", f"{base}/api/accounts/me", token=token, timeout=args.timeout)
        if status != 200 or "balance_cents" not in body:
            raise StepFailed(f"lecture du solde impossible (HTTP {status})")
        initial = int(body["balance_cents"])
        RESULT["balance_before_cents"] = initial
        report(2, "solde initial", True, f"{initial / 100:.2f} €")

        # 3. Envoi de 1,00 €
        status, body = call(
            "POST", f"{base}/api/transactions",
            {"recipient_email": args.recipient, "amount_cents": amount_cents, "message": "Smoke test"},
            token=token, headers={"Idempotency-Key": str(uuid.uuid4())}, timeout=args.timeout,
        )
        if status != 201 or "id" not in body:
            raise StepFailed(f"envoi refusé (HTTP {status}, {body.get('message', 'sans message')})")
        transaction_id = body["id"]
        RESULT["transaction"] = {"transaction_id": transaction_id, "reference": body.get("reference"), "amount_cents": amount_cents,
                                 "status": body.get("status"), "created_at": body.get("created_at"), "sender": args.email, "recipient": args.recipient}
        report(3, "envoi de 1,00 €", True, f"{body.get('reference', transaction_id)} -> {args.recipient}")

        # 4. Statut de la transaction
        status, body = call("GET", f"{base}/api/transactions/{transaction_id}", token=token, timeout=args.timeout)
        if status != 200 or body.get("status") != "completed":
            raise StepFailed(f"statut inattendu : HTTP {status}, status={body.get('status')}")
        RESULT["transaction"]["status"] = body["status"]
        report(4, "transaction terminée", True, body["status"])

        # 5. Solde débité
        status, body = call("GET", f"{base}/api/accounts/me", token=token, timeout=args.timeout)
        final = int(body.get("balance_cents", -1))
        RESULT["balance_after_cents"] = final
        if status != 200 or final != initial - amount_cents:
            raise StepFailed(f"solde attendu {(initial - amount_cents) / 100:.2f} €, obtenu {final / 100:.2f} €")
        report(5, "solde débité", True, f"{final / 100:.2f} €")
    except StepFailed as error:
        report(_failed_step_from_message(str(error)), "échec", False, str(error))
        return False

    # 6. Cohérence (uniquement si l'URL interne est fournie : hors gateway)
    if args.internal_url:
        try:
            status, body = call("GET", f"{args.internal_url.rstrip('/')}/internal/consistency", timeout=args.timeout)
            RESULT["consistency"] = body.get("status", "ko")
            report(6, "cohérence des soldes", status == 200 and body.get("status") == "ok", body.get("status", f"HTTP {status}"))
        except StepFailed as error:
            report(6, "cohérence des soldes", False, str(error))
    elif not args.json:
        print("--  étape 6 — cohérence des soldes : ignorée (pas de --internal-url)")

    return ok


def _failed_step_from_message(message: str) -> int:
    """Déduit le numéro d'étape du message d'erreur (pour l'affichage)."""
    if "login" in message:
        return 1
    if "solde" in message and "attendu" in message:
        return 5
    if "lecture du solde" in message:
        return 2
    if "envoi" in message:
        return 3
    if "statut" in message:
        return 4
    return 0


def main() -> int:
    # Console Windows en cp1252 : on remplace les caractères non encodables plutôt que de planter
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Smoke test de bout en bout de la plateforme Poupal (démo).")
    parser.add_argument("--base-url", default=os.environ.get("POUPAL_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--email", default=os.environ.get("SMOKE_EMAIL", "alex@poupal.demo"))
    parser.add_argument("--password", default=os.environ.get("SMOKE_PASSWORD") or os.environ.get("DEMO_PASSWORD"))
    parser.add_argument("--recipient", default=os.environ.get("SMOKE_RECIPIENT", "camille@poupal.demo"))
    parser.add_argument("--internal-url", default=os.environ.get("POUPAL_INTERNAL_URL"), help="ex. http://api:8000 (réseau Docker)")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="sortie JSON sur une ligne (utilisée par le moteur de remédiation)")
    args = parser.parse_args()

    if not args.password:
        print("KO  configuration — mot de passe manquant : --password, SMOKE_PASSWORD ou DEMO_PASSWORD")
        print("SMOKE KO")
        return 1

    if not args.json:
        print(f"Smoke test Poupal — {args.base_url}")
    success = run(args)
    RESULT["ok"] = success
    if args.json:
        print(json.dumps(RESULT, ensure_ascii=False))
    else:
        print("SMOKE OK" if success else "SMOKE KO")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
