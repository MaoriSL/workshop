"""
Corrélateur SIEM (service léger). Toutes les PERIOD secondes, il évalue chaque règle de
corrélation contre Loki et :
  - expose des métriques Prometheus (sources en alerte par règle, total d'événements de sécurité) ;
  - émet une ligne JSON event=security_alert vers stdout (reprise par Loki) à chaque nouvelle alerte ;
  - sert /api/alerts (alertes actives) pour le dashboard.
Lecture seule : le SIEM observe et corrèle, il n'agit pas (l'action reste au moteur de remédiation).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

sys.path.insert(0, "/app")
from app.rules import RULES  # noqa: E402

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100").rstrip("/")
PERIOD_S = float(os.environ.get("SIEM_PERIOD_S", "10"))
SERVICE_NAME = "poupal-siem"

logging.basicConfig(level="INFO", stream=sys.stdout)
_log = logging.getLogger("poupal.siem")


def emit(event: str, **fields) -> None:
    print(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                      "level": fields.pop("level", "INFO"), "service": SERVICE_NAME, "event": event, **fields}, ensure_ascii=False), flush=True)


REGISTRY = CollectorRegistry()
RULE_SOURCES = Gauge("poupal_siem_rule_sources", "Nombre de sources (IP) au-dessus du seuil pour une règle", ["rule", "severity"], registry=REGISTRY)
RULE_MAX = Gauge("poupal_siem_rule_max_count", "Valeur maximale observée pour une règle (toutes sources)", ["rule"], registry=REGISTRY)
ALERTS_TOTAL = Counter("poupal_siem_alerts_total", "Alertes de corrélation émises", ["rule", "severity"], registry=REGISTRY)
UP = Gauge("poupal_siem_loki_up", "1 si Loki répond", registry=REGISTRY)


def loki_query(logql: str, timeout: float = 5.0) -> list[dict]:
    url = f"{LOKI_URL}/loki/api/v1/query?" + urllib.parse.urlencode({"query": logql})
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    return data.get("data", {}).get("result", [])


class Siem:
    def __init__(self) -> None:
        self.active: dict[str, dict] = {}   # clé rule_id|ip -> alerte active
        self.history: list[dict] = []

    def evaluate(self) -> None:
        for rule in RULES:
            try:
                results = loki_query(rule.logql)
                UP.set(1)
            except Exception as exc:   # Loki indisponible : on réessaiera
                UP.set(0)
                _log.warning("loki indisponible: %s", str(exc)[:120])
                return
            over = []
            max_count = 0.0
            for series in results:
                try:
                    count = float(series["value"][1])
                except (KeyError, ValueError, IndexError):
                    continue
                max_count = max(max_count, count)
                ip = series.get("metric", {}).get("client_ip") or series.get("metric", {}).get("transaction_client_ip") or "?"
                if count >= rule.threshold:
                    over.append((ip, count))
                    self._raise(rule, ip, count)
            RULE_SOURCES.labels(rule.id, rule.severity).set(len(over))
            RULE_MAX.labels(rule.id).set(max_count)
            self._expire(rule, {ip for ip, _ in over})

    def _raise(self, rule, ip: str, count: float) -> None:
        key = f"{rule.id}|{ip}"
        if key not in self.active:
            alert = {"rule_id": rule.id, "rule": rule.name, "severity": rule.severity, "incident_hint": rule.incident_hint,
                     "source_ip": ip, "count": count, "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"), "threshold": rule.threshold}
            self.active[key] = alert
            self.history.append(alert)
            self.history = self.history[-200:]
            ALERTS_TOTAL.labels(rule.id, rule.severity).inc()
            emit("security_alert", level="WARNING", **alert)
        else:
            self.active[key]["count"] = count

    def _expire(self, rule, still_over: set[str]) -> None:
        for key in [k for k in self.active if k.startswith(f"{rule.id}|") and self.active[k]["source_ip"] not in still_over]:
            resolved = self.active.pop(key)
            emit("security_alert_resolved", rule_id=rule.id, source_ip=resolved["source_ip"])


siem = Siem()


def loop() -> None:
    emit("siem_started", rules=[r.id for r in RULES], loki=LOKI_URL)
    while True:
        try:
            siem.evaluate()
        except Exception as exc:
            _log.error("évaluation échouée: %s", str(exc)[:160])
        time.sleep(PERIOD_S)


app = FastAPI(title="Poupal - SIEM", docs_url=None, redoc_url=None, openapi_url=None)


@app.on_event("startup")
def _start() -> None:
    threading.Thread(target=loop, daemon=True).start()


@app.get("/api/alerts")
def alerts() -> dict:
    return {"active": list(siem.active.values()), "history": list(reversed(siem.history))[:50],
            "rules": [{"id": r.id, "name": r.name, "description": r.description, "severity": r.severity,
                       "threshold": r.threshold, "incident_hint": r.incident_hint} for r in RULES]}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready")
def ready() -> dict:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
