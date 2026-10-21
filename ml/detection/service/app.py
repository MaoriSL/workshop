"""
Détecteur d'anomalies temps réel Poupal (conteneur anomaly-detector).

Toutes les 5 s : lit les dernières minutes des règles d'enregistrement dans Prometheus,
calcule les variables avec features.py (le MÊME code qu'à l'entraînement), calcule le score
avec le modèle chargé, fait avancer la machine à états et, aux transitions ANOMALIE / NORMAL,
envoie un incident signé (HMAC) au moteur de remédiation.
Le détecteur DÉTECTE mais n'AGIT pas : lecture seule sur Prometheus, aucun accès à Docker.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets as pysecrets
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

from ..data import fetch_recent, list_recording_rules
from ..features import latest_features
from ..model import DetectionModel
from .state_machine import ANOMALY, NORMAL, StateMachine
from .webhook import send_incident

# ---------------------------------------------------------------- Configuration (variables d'environnement)
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/models"))
INTERVAL_S = float(os.environ.get("DETECTOR_INTERVAL_S", "5"))
HISTORY_MIN = float(os.environ.get("DETECTOR_HISTORY_MIN", "3"))
CONFIRM_N = int(os.environ.get("DETECTOR_CONFIRM_N", "2"))
CONFIRM_M = int(os.environ.get("DETECTOR_CONFIRM_M", "3"))
RECOVER_R = int(os.environ.get("DETECTOR_RECOVER_R", "6"))
REMEDIATION_URL = os.environ.get("REMEDIATION_URL", "").strip() or None
HMAC_SECRET = os.environ.get("REMEDIATION_HMAC_SECRET", "")
SERVICE_NAME = "poupal-detector"

STATE_CODES = {NORMAL: 0, "SUSPECT": 1, ANOMALY: 2, "RETABLISSEMENT": 3}

# ---------------------------------------------------------------- Logs JSON (même format que les services)
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "level": record.levelname,
                   "service": SERVICE_NAME, "message": record.getMessage()}
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, ensure_ascii=False, default=str)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), handlers=[handler])
logging.getLogger("uvicorn.access").disabled = True
logger = logging.getLogger("poupal.detector")


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": {"event": event, **fields}})


# ---------------------------------------------------------------- Métriques Prometheus
# Registre dédié (pas le registre global) : le module peut être rechargé sans doublon.
REGISTRY = CollectorRegistry()
ANOMALY_SCORE = Gauge("poupal_anomaly_score", "Score d'anomalie global (plus haut = plus anormal)", registry=REGISTRY)
ANOMALY_THRESHOLD = Gauge("poupal_anomaly_threshold", "Seuil d'alerte du modèle", registry=REGISTRY)
ANOMALY_STATE = Gauge("poupal_anomaly_state", "État du détecteur : 0 normal, 1 suspect, 2 anomalie, 3 rétablissement", registry=REGISTRY)
SERVICE_SCORE = Gauge("poupal_anomaly_service_score", "Score d'anomalie par service", ["service"], registry=REGISTRY)
MODEL_LOADED = Gauge("poupal_detector_model_loaded", "1 si le modèle est chargé", registry=REGISTRY)
PROMETHEUS_OK = Gauge("poupal_detector_prometheus_up", "1 si Prometheus répond", registry=REGISTRY)
LAST_CYCLE = Gauge("poupal_detector_last_cycle_timestamp", "Horodatage (epoch) du dernier cycle réussi", registry=REGISTRY)


# ---------------------------------------------------------------- État partagé
class Detector:
    def __init__(self) -> None:
        self.model: DetectionModel | None = None
        self.metadata: dict = {}
        self.rules: list[str] = []
        self.machine = StateMachine(confirm_n=CONFIRM_N, confirm_m=CONFIRM_M, recover_r=RECOVER_R)
        self.prometheus_ok = False
        self.last_score: float | None = None
        self.last_explanation: dict = {}
        self.last_service_scores: dict[str, float] = {}
        self.last_cycle_at: datetime | None = None
        self.current_incident: dict | None = None
        self.incidents: list[dict] = []

    def load_model(self) -> bool:
        try:
            self.model = joblib.load(MODEL_DIR / "model.joblib")
            self.metadata = json.loads((MODEL_DIR / "metadata.json").read_text(encoding="utf-8"))
            ANOMALY_THRESHOLD.set(self.model.threshold)
            MODEL_LOADED.set(1)
            log_event("model_loaded", version=self.model.version, features=len(self.model.feature_names), threshold=self.model.threshold)
            return True
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            MODEL_LOADED.set(0)
            log_event("model_unavailable", logging.ERROR, error=str(exc)[:200], model_dir=str(MODEL_DIR))
            return False

    def cycle(self) -> None:
        """Un passage : Prometheus → variables → score → machine à états → incident éventuel."""
        if self.model is None and not self.load_model():
            return
        try:
            if not self.rules:
                self.rules = list_recording_rules(PROMETHEUS_URL)
            raw = fetch_recent(PROMETHEUS_URL, self.rules, minutes=HISTORY_MIN, step_seconds=5)
            self.prometheus_ok = True
        except Exception as exc:  # réseau, JSON... : on reste en vie et on réessaie au cycle suivant
            self.prometheus_ok = False
            PROMETHEUS_OK.set(0)
            log_event("prometheus_unreachable", logging.WARNING, error=str(exc)[:200])
            return
        PROMETHEUS_OK.set(1)
        if raw.empty:
            log_event("no_data", logging.WARNING)
            return

        row = latest_features(raw, self.model.feature_names, window=self.model.window)
        frame = row.to_frame().T
        score = float(self.model.score(frame)[0])
        self.last_score = score
        self.last_service_scores = {s: float(v[0]) for s, v in self.model.service_scores(frame).items()}
        self.last_explanation = self.model.explain(row)
        self.last_cycle_at = datetime.now(timezone.utc)
        ANOMALY_SCORE.set(score)
        for service, value in self.last_service_scores.items():
            SERVICE_SCORE.labels(service).set(value)
        LAST_CYCLE.set(self.last_cycle_at.timestamp())

        transition = self.machine.update(score > self.model.threshold, now=self.last_cycle_at)
        ANOMALY_STATE.set(STATE_CODES[self.machine.state])
        if transition is None:
            return
        log_event("state_changed", previous=transition.previous, current=transition.current, score=round(score, 4))
        if transition.current == ANOMALY and self.current_incident is None:
            self.open_incident(score)
        elif transition.current == NORMAL and self.current_incident is not None:
            self.close_incident(score)

    # ---- incidents (contrat : docs/api/incident.md)
    def build_incident(self, state: str, score: float) -> dict:
        explanation = self.last_explanation or {}
        return {
            "incident_id": self.current_incident["incident_id"] if self.current_incident else f"inc-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{pysecrets.token_hex(2)}",
            "state": state,
            "detected_at": self.current_incident["detected_at"] if self.current_incident else self.machine.since.isoformat(timespec="milliseconds"),
            "resolved_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds") if state == NORMAL else None,
            "score": round(score, 4),
            "threshold": round(self.model.threshold, 4) if self.model else None,
            "suspected_service": explanation.get("suspected_service", "inconnu"),
            "incident_type": explanation.get("incident_type", "inconnu"),
            "top_features": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()} for f in explanation.get("top_features", [])],
            "model_version": self.model.version if self.model else None,
        }

    def open_incident(self, score: float) -> None:
        incident = self.build_incident(ANOMALY, score)
        self.current_incident = incident
        self.incidents.append(incident)
        log_event("anomaly_detected", logging.WARNING, **{k: v for k, v in incident.items() if k != "top_features"},
                  top_features=[f["name"] for f in incident["top_features"]])
        send_incident(REMEDIATION_URL, HMAC_SECRET, incident)

    def close_incident(self, score: float) -> None:
        incident = self.build_incident(NORMAL, score)
        incident["suspected_service"] = self.current_incident["suspected_service"]
        incident["incident_type"] = self.current_incident["incident_type"]
        self.incidents.append(incident)
        self.current_incident = None
        log_event("anomaly_resolved", **{k: v for k, v in incident.items() if k != "top_features"})
        send_incident(REMEDIATION_URL, HMAC_SECRET, incident)

    def status(self) -> dict:
        explanation = self.last_explanation or {}
        return {
            "state": self.machine.state,
            "since": self.machine.since.isoformat(timespec="seconds"),
            "score": None if self.last_score is None else round(self.last_score, 4),
            "threshold": None if self.model is None else round(self.model.threshold, 4),
            "suspected_service": explanation.get("suspected_service"),
            "incident_type": explanation.get("incident_type"),
            "top_features": explanation.get("top_features", []),
            "service_scores": {k: round(v, 4) for k, v in self.last_service_scores.items()},
            "service_votes": explanation.get("service_votes", {}),
            "current_incident": self.current_incident,
            "model_version": None if self.model is None else self.model.version,
            "prometheus_ok": self.prometheus_ok,
            "last_cycle_at": None if self.last_cycle_at is None else self.last_cycle_at.isoformat(timespec="seconds"),
            "config": {"interval_s": INTERVAL_S, "confirm_n": CONFIRM_N, "confirm_m": CONFIRM_M, "recover_r": RECOVER_R,
                       "remediation_url_configured": REMEDIATION_URL is not None},
        }


detector = Detector()


async def run_loop() -> None:
    """Boucle de fond : un cycle toutes les INTERVAL_S secondes (le calcul tourne dans un thread)."""
    while True:
        started = time.monotonic()
        try:
            await asyncio.to_thread(detector.cycle)
        except Exception as exc:  # jamais laisser mourir la boucle
            log_event("cycle_failed", logging.ERROR, error=str(exc)[:200])
        await asyncio.sleep(max(0.5, INTERVAL_S - (time.monotonic() - started)))


@asynccontextmanager
async def lifespan(_: FastAPI):
    detector.load_model()          # peut échouer : readiness = false, on réessaie à chaque cycle
    task = asyncio.create_task(run_loop())
    log_event("detector_started", prometheus_url=PROMETHEUS_URL, interval_s=INTERVAL_S, remediation_url_configured=REMEDIATION_URL is not None)
    yield
    task.cancel()


app = FastAPI(title="Poupal - Détecteur d'anomalies", version="0.1.0", lifespan=lifespan,
              description="Environnement de démonstration (plateforme fictive). Détecte, n'agit pas.")


@app.get("/status")
def status() -> dict:
    return detector.status()


@app.get("/incidents")
def incidents() -> dict:
    return {"count": len(detector.incidents), "items": detector.incidents[-100:]}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready")
def ready() -> JSONResponse:
    checks = {"model": detector.model is not None, "prometheus": detector.prometheus_ok}
    ok = all(checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ok" if ok else "ko", "checks": checks})


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
