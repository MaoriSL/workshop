"""Garde-fous du moteur de remédiation : signature, idempotence, listes blanches, escalade, arrêt, disjoncteur."""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("REMEDIATION_HMAC_SECRET", "test-secret")
os.environ["REMEDIATION_DRY_RUN"] = "false"
os.environ["REMEDIATION_MIN_DELAY_S"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import executor, main, verifier  # noqa: E402
from app.state import ECHEC, RETABLI, CircuitBreaker  # noqa: E402

SECRET = os.environ["REMEDIATION_HMAC_SECRET"]


def signed(payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return body, {"X-Poupal-Signature": "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}


def incident(**over) -> dict:
    base = {"incident_id": f"inc-test-{int(time.time() * 1000)}", "state": "ANOMALIE", "detected_at": datetime.now(timezone.utc).isoformat(),
            "score": 0.9, "threshold": 0.5, "suspected_service": "poupal-api", "incident_type": "indisponibilite", "top_features": [], "model_version": "t"}
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def fresh_engine(monkeypatch):
    main.engine = main.Engine()
    # Exécution et vérification simulées (pas de Docker ni d'Ansible dans les tests unitaires)
    calls = []
    monkeypatch.setattr(executor, "execute", lambda action, params: (calls.append(action) or executor.ActionResult(action, params, True, 0.1, "ok")))
    monkeypatch.setattr(verifier, "verify", lambda service: verifier.Verification(healthy=True, smoke_ok=True, consistency_ok=True, proof={"reference": "PP-TEST", "amount_cents": 100}))
    yield calls


def wait_terminal(incident_id: str, timeout: float = 5.0):
    for _ in range(int(timeout * 20)):
        inc = main.engine.registry.get(incident_id)
        if inc and not inc.is_open:
            return inc
        time.sleep(0.05)
    raise AssertionError("incident toujours ouvert")


def test_unsigned_incident_is_refused():
    client = TestClient(main.app)
    body, _ = signed(incident())
    assert client.post("/incidents", content=body, headers={"Content-Type": "application/json"}).status_code == 401
    assert client.post("/incidents", content=body, headers={"X-Poupal-Signature": "sha256=deadbeef", "Content-Type": "application/json"}).status_code == 401
    assert main.engine.registry.last() is None


def test_same_incident_id_is_handled_once(fresh_engine):
    client = TestClient(main.app)
    body, headers = signed(incident(incident_id="inc-dup"))
    assert client.post("/incidents", content=body, headers=headers).status_code == 202
    wait_terminal("inc-dup")
    assert client.post("/incidents", content=body, headers=headers).json()["status"] == "already_known"
    assert fresh_engine == ["restart_service"]        # une seule remédiation


def test_recovered_with_proof_in_one_action():
    client = TestClient(main.app)
    body, headers = signed(incident(incident_id="inc-ok"))
    client.post("/incidents", content=body, headers=headers)
    inc = wait_terminal("inc-ok")
    assert inc.state == RETABLI and inc.proof["reference"] == "PP-TEST"
    steps = [s.step for s in inc.timeline]
    assert steps == ["detected", "received", "decided", "action_started", "action_done", "verification_started", "healthy", "proof_transaction", "consistency_ok", "recovered"]


def test_escalation_when_verification_fails_then_stops_after_three_actions(monkeypatch, fresh_engine):
    monkeypatch.setattr(verifier, "verify", lambda service: verifier.Verification(healthy=True, smoke_ok=False, details=["x", "smoke test KO"]))
    client = TestClient(main.app)
    body, headers = signed(incident(incident_id="inc-esc"))
    client.post("/incidents", content=body, headers=headers)
    inc = wait_terminal("inc-esc")
    assert inc.state == ECHEC and inc.actions_done == 3
    assert fresh_engine == ["restart_service", "recreate_service", "rollback"]
    assert [s.step for s in inc.timeline].count("escalated") == 3


def test_service_outside_whitelist_is_refused():
    client = TestClient(main.app)
    body, headers = signed(incident(suspected_service="grafana"))
    assert client.post("/incidents", content=body, headers=headers).status_code == 422
    body, headers = signed(incident(incident_type="rm -rf"))
    assert client.post("/incidents", content=body, headers=headers).status_code == 422


def test_invalid_or_internal_ip_is_refused():
    with pytest.raises(executor.ActionRefused):
        executor.validate_ip("not-an-ip")
    with pytest.raises(executor.ActionRefused):
        executor.validate_ip("172.19.0.5")          # réseau Docker : notre infrastructure
    with pytest.raises(executor.ActionRefused):
        executor.validate_ip("127.0.0.1")
    assert executor.validate_ip("203.0.113.42") == "203.0.113.42"


def test_circuit_breaker_opens_at_threshold():
    breaker = CircuitBreaker(limit=3, window_minutes=10)
    for _ in range(2):
        breaker.record()
    assert not breaker.open
    breaker.record()
    assert breaker.open
    old = CircuitBreaker(limit=1, window_minutes=1)
    old.record(datetime.now(timezone.utc) - timedelta(minutes=5))
    assert not old.open                             # hors fenêtre : oublié


def test_breaker_open_means_no_action(fresh_engine):
    main.engine.breaker = CircuitBreaker(limit=1, window_minutes=10)
    main.engine.breaker.record()
    client = TestClient(main.app)
    body, headers = signed(incident(incident_id="inc-safe"))
    client.post("/incidents", content=body, headers=headers)
    inc = wait_terminal("inc-safe")
    assert inc.state == ECHEC and fresh_engine == [] and "SÛRETÉ" in inc.timeline[-1].label
