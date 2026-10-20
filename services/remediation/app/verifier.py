"""
Vérification de la reprise : LA PREUVE. Après chaque action, dans cet ordre :
  1. le service est de nouveau healthy (sondes HTTP directes, Prometheus pour la base) ;
  2. scripts/smoke_test.py : une NOUVELLE transaction fictive aboutit (login → virement →
     solde débité) — c'est le même script que celui de l'exploitation, en sortie JSON ;
  3. /internal/consistency : aucun solde négatif, somme des soldes conservée.
Les trois doivent réussir pour déclarer la reprise ; sinon, escalade.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("poupal.remediation.verifier")

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:80").rstrip("/")
API_INTERNAL_URL = os.environ.get("API_INTERNAL_URL", "http://api:8000").rstrip("/")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
SMOKE_TEST = os.environ.get("SMOKE_TEST_PATH", "/app/scripts/smoke_test.py")
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
HEALTHY_TIMEOUT_S = float(os.environ.get("REMEDIATION_HEALTHY_TIMEOUT_S", "25"))

# Sondes de vivacité par service (directes, sans passer par la gateway sauf pour le front)
PROBES = {
    "auth": f"http://auth:8001/ready",
    "api": f"http://api:8000/ready",
    "front": f"http://front:80/healthz",
    "gateway": f"{GATEWAY_URL}/gateway/health",
}


@dataclass
class Verification:
    healthy: bool = False
    smoke_ok: bool = False
    consistency_ok: bool = False
    proof: dict | None = None
    details: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.healthy and self.smoke_ok and self.consistency_ok


def probe(service: str, timeout: float = 3.0) -> bool:
    if service == "db":
        try:
            r = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "max(pg_up)"}, timeout=timeout)
            result = r.json().get("data", {}).get("result", [])
            return bool(result) and float(result[0]["value"][1]) == 1.0
        except (httpx.HTTPError, ValueError, KeyError):
            return False
    url = PROBES.get(service)
    if not url:
        return True
    try:
        return httpx.get(url, timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False


def wait_healthy(service: str, timeout_s: float = HEALTHY_TIMEOUT_S, interval: float = 1.0) -> tuple[bool, float]:
    """Attend que la sonde du service réponde (≤ timeout). Renvoie (ok, secondes attendues)."""
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        if probe(service):
            return True, round(time.monotonic() - started, 1)
        time.sleep(interval)
    return False, round(time.monotonic() - started, 1)


def run_smoke_test(timeout_s: float = 20.0) -> dict:
    """Exécute scripts/smoke_test.py --json : transaction de preuve ou raison de l'échec."""
    cmd = [sys.executable, SMOKE_TEST, "--base-url", GATEWAY_URL, "--internal-url", API_INTERNAL_URL, "--json", "--timeout", "5"]
    env = {**os.environ, "SMOKE_PASSWORD": SMOKE_PASSWORD}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env)
        line = next((l for l in reversed(proc.stdout.strip().splitlines()) if l.startswith("{")), "{}")
        result = json.loads(line)
        result.setdefault("ok", False)
        return result
    except (subprocess.TimeoutExpired, json.JSONDecodeError, StopIteration) as exc:
        return {"ok": False, "steps": [], "error": f"smoke test : {str(exc)[:120]}"}


def check_consistency(timeout: float = 5.0) -> tuple[bool, dict]:
    try:
        r = httpx.get(f"{API_INTERNAL_URL}/internal/consistency", timeout=timeout)
        payload = r.json()
        return r.status_code == 200 and payload.get("status") == "ok", payload
    except (httpx.HTTPError, ValueError):
        return False, {}


def verify(service: str) -> Verification:
    """Les trois contrôles, dans l'ordre ; s'arrête au premier échec (escalade)."""
    started = time.monotonic()
    v = Verification()
    v.healthy, waited = wait_healthy(service)
    v.details.append(f"{service} healthy en {waited} s" if v.healthy else f"{service} toujours indisponible après {waited} s")
    if v.healthy:
        smoke = run_smoke_test()
        v.smoke_ok = bool(smoke.get("ok"))
        failed = [s for s in smoke.get("steps", []) if not s.get("ok")]
        v.details.append("nouvelle transaction réussie" if v.smoke_ok else f"smoke test KO : {failed[0]['detail'] if failed else smoke.get('error', '?')}")
        if v.smoke_ok:
            v.proof = {**(smoke.get("transaction") or {}), "balance_before_cents": smoke.get("balance_before_cents"),
                       "balance_after_cents": smoke.get("balance_after_cents"), "consistency": None}
            v.consistency_ok, payload = check_consistency()
            v.proof["consistency"] = "ok" if v.consistency_ok else "ko"
            v.details.append("cohérence des soldes : ok" if v.consistency_ok else f"cohérence KO : {json.dumps(payload.get('checks', {}))[:160]}")
    v.duration_s = round(time.monotonic() - started, 1)
    logger.info("verification", extra={"fields": {"event": "verification", "service": service, "healthy": v.healthy, "smoke_ok": v.smoke_ok, "consistency_ok": v.consistency_ok, "duration_s": v.duration_s}})
    return v
