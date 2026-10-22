"""
Moteur de remédiation automatique Poupal — API FastAPI + flux d'événements.

Reçoit les incidents signés du détecteur (POST /incidents), décide (policy), agit (executor,
playbooks Ansible via ansible-runner), PROUVE la reprise (verifier : service healthy +
nouvelle transaction réussie + cohérence des soldes), et expose l'état consolidé au
dashboard (GET /api/state, SSE /api/events). Aucune interface d'administration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from pydantic import ValidationError

from . import executor, verifier
from .policy import SERVICES, build_plan, describe, family, normalize_service
from .receiver import SIGNATURE_HEADER, IncidentIn, verify_signature
from .state import (ACTION_EN_COURS, DECIDE, ECHEC, ESCALADE, MAX_ACTIONS_PER_INCIDENT, RECU, RETABLI, VERIFICATION,
                    CircuitBreaker, Incident, Registry, now)

SERVICE_NAME = "poupal-remediation"
HMAC_SECRET = os.environ.get("REMEDIATION_HMAC_SECRET", "")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
DETECTOR_URL = os.environ.get("DETECTOR_URL", "http://anomaly-detector:8010").rstrip("/")
MIN_DELAY_BETWEEN_ACTIONS_S = float(os.environ.get("REMEDIATION_MIN_DELAY_S", "5"))
BREAKER_LIMIT = int(os.environ.get("REMEDIATION_BREAKER_LIMIT", "8"))
BREAKER_WINDOW_MIN = int(os.environ.get("REMEDIATION_BREAKER_WINDOW_MIN", "10"))


# ---------------------------------------------------------------- Logs JSON
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": record.levelname,
                   "service": SERVICE_NAME, "message": record.getMessage()}
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, ensure_ascii=False, default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), handlers=[_handler])
logging.getLogger("uvicorn.access").disabled = True
logger = logging.getLogger("poupal.remediation")


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": {"event": event, **fields}})


# ---------------------------------------------------------------- Métriques
REGISTRY = CollectorRegistry()
ACTIONS = Counter("poupal_remediation_actions_total", "Actions de remédiation par résultat", ["action", "result"], registry=REGISTRY)
RECOVERY = Histogram("poupal_recovery_duration_seconds", "Durée détection → reprise prouvée", buckets=(10, 20, 30, 45, 60, 90, 120, 300), registry=REGISTRY)
INCIDENTS = Counter("poupal_remediation_incidents_total", "Incidents reçus par résultat final", ["result"], registry=REGISTRY)
STATE_GAUGE = Gauge("poupal_remediation_state", "État global : 0 normal, 1 anomalie, 2 remédiation, 3 rétabli, 4 échec, 5 sûreté", registry=REGISTRY)
BREAKER_GAUGE = Gauge("poupal_remediation_breaker_open", "1 si le disjoncteur est ouvert", registry=REGISTRY)
REJECTED = Counter("poupal_remediation_rejected_total", "Incidents refusés", ["reason"], registry=REGISTRY)
GLOBAL_CODES = {"NORMAL": 0, "ANOMALIE": 1, "REMEDIATION": 2, "RETABLI": 3, "ECHEC": 4, "SURETE": 5}


# ---------------------------------------------------------------- État partagé + bus d'événements
class Engine:
    def __init__(self) -> None:
        self.registry = Registry()
        self.breaker = CircuitBreaker(limit=BREAKER_LIMIT, window_minutes=BREAKER_WINDOW_MIN)
        self.lock = threading.Lock()                 # un seul incident traité à la fois par service
        self.service_locks: dict[str, threading.Lock] = {s: threading.Lock() for s in SERVICES}
        self.version = 0                             # incrémenté à chaque changement (SSE)
        self.last_proof: dict | None = None
        self.markers: list[dict] = []
        self.last_action_at: float = 0.0

    def changed(self) -> None:
        self.version += 1

    def global_state(self) -> str:
        if self.breaker.open:
            return "SURETE"
        current = self.registry.current()
        if current is not None:
            return "ANOMALIE" if current.state in (RECU, DECIDE) else "REMEDIATION"
        last = self.registry.last()
        if last is not None and last.resolved_at and (now() - last.resolved_at).total_seconds() < 120:
            return "RETABLI" if last.state == RETABLI else "ECHEC"
        return "NORMAL"

    def marker(self, kind: str, label: str) -> None:
        self.markers.append({"t": now().isoformat(timespec="seconds"), "kind": kind, "label": label})
        self.markers = self.markers[-30:]


engine = Engine()


# ---------------------------------------------------------------- Traitement d'un incident (thread)
def handle_incident(incident: Incident) -> None:
    """RECU → DECIDE → (ACTION_EN_COURS → VERIFICATION)×n → RETABLI | ECHEC. Un thread par incident, un verrou par service."""
    service = incident.suspected_service
    lock = engine.service_locks.get(service, engine.lock)
    with lock:
        try:
            _process(incident)
        except Exception as exc:  # jamais laisser un incident sans état final
            log_event("incident_crashed", logging.ERROR, incident_id=incident.incident_id, error=str(exc)[:200])
            incident.add_step("failed", f"Erreur interne du moteur : {str(exc)[:80]}")
            incident.finish_failed("erreur interne")
            INCIDENTS.labels("error").inc()
        finally:
            engine.changed()


def _process(incident: Incident) -> None:
    # Disjoncteur : trop de remédiations récentes → on n'agit plus, on signale
    if engine.breaker.open:
        incident.add_step("failed", "Disjoncteur ouvert : mode SÛRETÉ, aucune action automatique", breaker=engine.breaker.to_dict())
        incident.finish_failed("disjoncteur ouvert")
        INCIDENTS.labels("breaker").inc()
        log_event("remediation_breaker_open", logging.ERROR, incident_id=incident.incident_id)
        return

    # DECIDE : plan tiré du catalogue (jamais une commande venue de l'extérieur)
    incident.plan = build_plan(incident.incident_type, service_for_plan(incident))
    incident.set_state(DECIDE)
    incident.add_step("decided", f"Plan choisi ({family(incident.incident_type)}) : {describe(incident.plan)}", plan=incident.plan, family=family(incident.incident_type))
    log_event("remediation_decided", incident_id=incident.incident_id, incident_type=incident.incident_type, service=incident.suspected_service, plan=describe(incident.plan))
    engine.changed()

    for step in incident.plan:
        if incident.actions_done >= MAX_ACTIONS_PER_INCIDENT:
            break
        # Délai minimum entre deux actions (stabilisation)
        wait = MIN_DELAY_BETWEEN_ACTIONS_S - (time.monotonic() - engine.last_action_at)
        if incident.actions_done > 0 and wait > 0:
            time.sleep(wait)

        incident.current_level = step["level"]
        incident.set_state(ACTION_EN_COURS)
        incident.add_step("action_started", f"Niveau {step['level']} : {step['action']} — {step['why']}", action=step["action"], params=step["params"])
        engine.marker("action", f"{step['action']} (n{step['level']})")
        engine.changed()
        try:
            result = executor.execute(step["action"], step["params"])
        except executor.ActionRefused as exc:
            result = executor.ActionResult(step["action"], step["params"], False, 0.0, f"refusé : {exc}", skipped=True)
        engine.last_action_at = time.monotonic()
        if not result.skipped:
            incident.actions_done += 1
            engine.breaker.record()
            for playbook in step["action"].split("+"):
                ACTIONS.labels(playbook, "ok" if result.ok else "ko").inc()
        incident.add_step("action_done", f"{step['action']} : {'OK' if result.ok else ('sautée' if result.skipped else 'ÉCHEC')} ({result.duration_s} s)", result=result.to_dict())
        engine.changed()

        if result.ok and not result.skipped:
            incident.set_state(VERIFICATION)
            incident.add_step("verification_started", "Vérification : service healthy → nouvelle transaction → cohérence des soldes")
            engine.changed()
            target = step["params"].get("service") or incident.suspected_service
            verification = verifier.verify(target if target in SERVICES else "api")
            if verification.healthy:
                incident.add_step("healthy", verification.details[0] if verification.details else f"{target} de nouveau healthy")
            if verification.smoke_ok and verification.proof:
                proof = verification.proof
                incident.add_step("proof_transaction", f"NOUVELLE TRANSACTION RÉUSSIE : {proof.get('amount_cents', 0) / 100:.2f} € ({proof.get('reference')})", proof=proof)
            if verification.consistency_ok:
                incident.add_step("consistency_ok", "Cohérence des soldes vérifiée : aucun solde négatif, somme conservée")
            engine.changed()
            if verification.ok:
                incident.finish_recovered(verification.proof)
                incident.add_step("recovered", f"SERVICE RÉTABLI en {incident.recovery_seconds} s (détection → preuve)", recovery_seconds=incident.recovery_seconds)
                engine.last_proof = {**verification.proof, "incident_id": incident.incident_id}
                engine.marker("recovered", f"rétabli {incident.recovery_seconds}s")
                RECOVERY.observe(incident.recovery_seconds or 0)
                INCIDENTS.labels("recovered").inc()
                log_event("remediation_recovered", incident_id=incident.incident_id, service=incident.suspected_service,
                          recovery_seconds=incident.recovery_seconds, proof_reference=verification.proof.get("reference"))
                return
            reason = next((d for d in reversed(verification.details)), "vérification échouée")
        else:
            reason = result.details
        incident.set_state(ESCALADE)
        incident.add_step("escalated", f"Vérification non concluante ({reason[:120]}) : escalade au niveau suivant")
        engine.changed()

    incident.finish_failed(f"{incident.actions_done} action(s) sans reprise prouvée")
    incident.add_step("failed", f"REMÉDIATION EN ÉCHEC après {incident.actions_done} action(s) : intervention requise")
    engine.marker("failed", "échec")
    INCIDENTS.labels("failed").inc()
    log_event("remediation_failed", logging.ERROR, incident_id=incident.incident_id, service=incident.suspected_service, actions=incident.actions_done)


def service_for_plan(incident: Incident) -> str:
    return incident.suspected_service if incident.suspected_service in SERVICES else "api"


# ---------------------------------------------------------------- Agrégation pour le dashboard
def prom_query(query: str, timeout: float = 3.0) -> list[dict]:
    try:
        r = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=timeout)
        return r.json().get("data", {}).get("result", [])
    except (httpx.HTTPError, ValueError):
        return []


def _by_label(results: list[dict], label: str) -> dict[str, float]:
    return {r["metric"].get(label, "").replace("poupal-", ""): float(r["value"][1]) for r in results}


def services_health() -> list[dict]:
    """Santé de chaque service lue dans Prometheus (règles poupal:*)."""
    up = _by_label(prom_query("poupal:service_up"), "job")
    p95 = _by_label(prom_query("poupal:http_latency_seconds:p95"), "service")
    err = _by_label(prom_query("poupal:http_error_ratio_5xx:rate1m"), "service")
    rps = _by_label(prom_query("poupal:http_requests_per_second:rate1m"), "service")
    rps.update(_by_label(prom_query("poupal:gateway_requests_per_second:rate1m"), "service"))
    tiles = []
    for name in SERVICES:
        is_up = up.get("gateway") if name == "front" else up.get(name)   # le front n'est pas scrapé : état de la gateway
        tiles.append({"name": name, "up": None if is_up is None else is_up >= 1.0,
                      "latency_p95_ms": None if name not in p95 else round(p95[name] * 1000, 1),
                      "error_rate_5xx": None if name not in err else round(err[name], 4),
                      "requests_per_s": None if name not in rps else round(rps[name], 2)})
    return tiles


def detector_status() -> dict:
    try:
        d = httpx.get(f"{DETECTOR_URL}/status", timeout=2.0).json()
        return {"available": True, "state": d.get("state"), "score": d.get("score"), "threshold": d.get("threshold"),
                "suspected_service": d.get("suspected_service"), "incident_type": d.get("incident_type")}
    except (httpx.HTTPError, ValueError):
        return {"available": False, "state": None, "score": None, "threshold": None, "suspected_service": None, "incident_type": None}


def score_history(minutes: int = 10, step: int = 5) -> list[dict]:
    end = time.time()
    params = {"start": end - minutes * 60, "end": end, "step": step}
    try:
        s = httpx.get(f"{PROMETHEUS_URL}/api/v1/query_range", params={**params, "query": "poupal_anomaly_score"}, timeout=3.0).json()
        t = httpx.get(f"{PROMETHEUS_URL}/api/v1/query_range", params={**params, "query": "poupal_anomaly_threshold"}, timeout=3.0).json()
        scores = s["data"]["result"][0]["values"] if s["data"]["result"] else []
        thresholds = dict(t["data"]["result"][0]["values"]) if t["data"]["result"] else {}
        default = float(next(iter(thresholds.values()), 0))
        return [{"t": datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(timespec="seconds"), "score": float(v),
                 "threshold": float(thresholds.get(ts, default))} for ts, v in scores]
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return []


def build_state() -> dict:
    state = engine.global_state()
    STATE_GAUGE.set(GLOBAL_CODES[state])
    BREAKER_GAUGE.set(1 if engine.breaker.open else 0)
    current, last = engine.registry.current(), engine.registry.last()
    return {"global_state": state, "updated_at": now().isoformat(timespec="milliseconds"), "services": services_health(),
            "detector": detector_status(), "current_incident": current.to_dict() if current else None,
            "last_incident": last.to_dict() if last else None, "last_proof": engine.last_proof,
            "circuit_breaker": engine.breaker.to_dict(), "dry_run": executor.DRY_RUN,
            "score_history": score_history(), "markers": engine.markers}


# ---------------------------------------------------------------- API
app = FastAPI(title="Poupal - Moteur de remédiation", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None,
              description="Zero-touch : reçoit les incidents signés du détecteur, répare, prouve. Aucune interface d'administration.")


@app.post("/incidents")
async def receive_incident(request: Request) -> JSONResponse:
    body = await request.body()
    if not verify_signature(body, HMAC_SECRET, request.headers.get(SIGNATURE_HEADER)):
        REJECTED.labels("signature").inc()
        log_event("incident_rejected", logging.WARNING, reason="signature", client=request.client.host if request.client else None)
        return JSONResponse(status_code=401, content={"message": "Signature absente ou invalide.", "code": "invalid_signature"})
    try:
        incident_in = IncidentIn.model_validate_json(body)
    except ValidationError as exc:
        REJECTED.labels("validation").inc()
        return JSONResponse(status_code=422, content={"message": "Incident hors contrat.", "code": "validation_error", "errors": [e["msg"] for e in exc.errors()][:5]})

    existing = engine.registry.get(incident_in.incident_id)
    if incident_in.state == "NORMAL":
        if existing:
            existing.detector_normal_at = now()
            existing.add_step("detector_normal", "Le détecteur confirme le retour à la normale")
            engine.changed()
        return JSONResponse(status_code=200, content={"status": "noted", "incident_id": incident_in.incident_id})
    if existing:   # idempotence : un même incident_id ne déclenche qu'une seule remédiation
        return JSONResponse(status_code=200, content={"status": "already_known", "incident_id": incident_in.incident_id, "state": existing.state})
    service = incident_in.suspected_service if incident_in.suspected_service != "inconnu" else "api"
    if engine.registry.open_for_service(service):
        return JSONResponse(status_code=202, content={"status": "queued_behind_open_incident", "incident_id": incident_in.incident_id})

    incident = Incident(incident_id=incident_in.incident_id, incident_type=incident_in.incident_type, suspected_service=service,
                        detected_at=incident_in.detected_at, received_at=now(), score=incident_in.score, threshold=incident_in.threshold,
                        top_features=[f.model_dump() for f in incident_in.top_features])
    incident.add_step("detected", f"Anomalie détectée par le modèle ML : {incident.incident_type} sur {service} (score {incident.score:.3f})")
    incident.add_step("received", "Incident signé reçu par le moteur de remédiation")
    engine.registry.add(incident)
    engine.marker("detected", f"{incident.incident_type} / {service}")
    engine.changed()
    log_event("incident_received", incident_id=incident.incident_id, incident_type=incident.incident_type, service=service, score=incident.score)
    threading.Thread(target=handle_incident, args=(incident,), name=f"incident-{incident.incident_id}", daemon=True).start()
    return JSONResponse(status_code=202, content={"status": "accepted", "incident_id": incident.incident_id})


@app.get("/api/state")
async def api_state() -> dict:
    return await asyncio.to_thread(build_state)


@app.get("/api/incidents")
async def api_incidents() -> dict:
    return {"items": [i.to_dict() for i in engine.registry.history()]}


@app.get("/api/blocked-ips")
async def api_blocked_ips() -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content={"items": await asyncio.to_thread(executor.blocked_ips)})
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"message": str(exc), "code": "blocklist_unavailable"})


@app.post("/api/blocked-ips/{ip:path}/unblock")
async def api_unblock_ip(ip: str) -> JSONResponse:
    try:
        normalized = executor.validate_ip(ip)
        result = await asyncio.to_thread(executor.run_playbook, "unblock_ip", {"ip": normalized})
    except executor.ActionRefused as exc:
        return JSONResponse(status_code=400, content={"message": str(exc), "code": "invalid_ip"})
    if not result.ok:
        return JSONResponse(status_code=502, content={"message": result.details, "code": "unblock_failed"})
    engine.changed()
    return JSONResponse(status_code=200, content={"ip": normalized, "message": "Adresse IP débloquée."})


@app.get("/api/events")
async def api_events() -> StreamingResponse:
    """Server-Sent Events : l'état complet à chaque changement et toutes les 2 s (battement de cœur)."""
    async def stream():
        last_version, last_sent = -1, 0.0
        while True:
            if engine.version != last_version or time.monotonic() - last_sent >= 2.0:
                last_version, last_sent = engine.version, time.monotonic()
                state = await asyncio.to_thread(build_state)
                yield f"event: state\ndata: {json.dumps(state, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready")
def ready() -> JSONResponse:
    checks = {"hmac_secret": bool(HMAC_SECRET)}
    try:
        checks["runner"] = executor.DRY_RUN or httpx.get(f"{executor.RUNNER_URL}/health", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        checks["runner"] = False
    ok = all(checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ok" if ok else "ko", "checks": checks})


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    STATE_GAUGE.set(GLOBAL_CODES[engine.global_state()])
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@asynccontextmanager
async def lifespan(_: FastAPI):
    log_event("remediation_started", dry_run=executor.DRY_RUN, runner_url=executor.RUNNER_URL, breaker=engine.breaker.to_dict())
    yield


app.router.lifespan_context = lifespan
