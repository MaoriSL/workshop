"""
Orchestrateur de la console d'attaque (FastAPI) — tourne sur le PC Attaquant.

Rôle : exposer l'état et piloter les scénarios de la LISTE BLANCHE, en refusant toute cible hors
du périmètre autorisé (voir target.py). Aucune commande arbitraire : seuls des scénarios connus,
avec des paramètres bornés. Journalise chaque attaque (export CSV) et écrit sa fenêtre dans
ml/data/labels.csv pour la détection.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

sys.path.insert(0, "/app")
from scenarios import SCENARIOS  # noqa: E402

from .labels import SCENARIO_TO_LABEL  # noqa: E402
from .runner import RunManager  # noqa: E402
from .target import TARGET_URL, check_target, normalize_target  # noqa: E402

SERVICE_NAME = "poupal-attack-console"

logging.basicConfig(level="INFO", format='{"service":"%(name)s","level":"%(levelname)s","message":"%(message)s"}')
logger = logging.getLogger("attack-console")

target_url = TARGET_URL
in_lab, lab_reason = check_target(target_url)
manager = RunManager(target_url)
_version = 0
_emergency = False


def bump() -> None:
    global _version
    _version += 1


manager.on_change = bump


def build_state() -> dict:
    return {
        "target": target_url,
        "in_lab": in_lab,
        "lab_reason": lab_reason,
        "emergency_stopped": _emergency,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "scenarios": [s.to_dict() for s in SCENARIOS.values()],
        "runs": [r.to_dict() for r in manager.recent()],
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(json.dumps({"event": "console_started", "target": TARGET_URL, "in_lab": in_lab, "reason": lab_reason}))
    yield
    manager.stop_all()


app = FastAPI(title="Poupal - Console d'attaque (laboratoire)", version="0.1.0",
              docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/api/state")
def api_state() -> dict:
    return build_state()


@app.get("/api/scenarios")
def api_scenarios() -> dict:
    return {"items": [s.to_dict() for s in SCENARIOS.values()]}


@app.post("/api/scenarios/{scenario_id}/start")
async def api_start(scenario_id: str, request: Request) -> JSONResponse:
    global _emergency
    if scenario_id not in SCENARIOS:
        return JSONResponse(status_code=404, content={"message": "Scénario inconnu."})
    if not in_lab:
        return JSONResponse(status_code=403, content={"message": f"Cible hors périmètre : {lab_reason}", "code": "out_of_scope"})
    if manager.active(scenario_id) is not None:
        return JSONResponse(status_code=409, content={"message": "Ce scénario est déjà en cours."})
    body = {}
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        pass
    run = manager.start(scenario_id, (body or {}).get("params", {}))
    _emergency = False
    logger.info(json.dumps({"event": "attack_started", "scenario": scenario_id, "run_id": run.run_id, "params": run.params}))
    return JSONResponse(status_code=202, content={"run_id": run.run_id})


@app.post("/api/target")
async def api_target(request: Request) -> JSONResponse:
    global target_url, in_lab, lab_reason
    try:
        body = await request.json()
        requested_target = normalize_target(str((body or {}).get("url", "")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return JSONResponse(status_code=400, content={"message": str(exc), "code": "invalid_target"})
    if manager.any_active():
        return JSONResponse(status_code=409, content={"message": "Impossible de modifier la cible pendant une attaque.", "code": "attack_in_progress"})
    target_url = requested_target
    in_lab, lab_reason = check_target(target_url)
    manager.set_target(target_url)
    bump()
    logger.info(json.dumps({"event": "target_changed", "target": target_url, "in_lab": in_lab, "reason": lab_reason}))
    return JSONResponse(status_code=200, content={"target": target_url, "in_lab": in_lab, "lab_reason": lab_reason})


@app.post("/api/scenarios/{scenario_id}/stop")
def api_stop(scenario_id: str) -> JSONResponse:
    stopped = manager.stop(scenario_id)
    logger.info(json.dumps({"event": "attack_stopped", "scenario": scenario_id}))
    return JSONResponse(status_code=200, content={"stopped": stopped})


@app.post("/api/stop-all")
def api_stop_all() -> JSONResponse:
    global _emergency
    count = manager.stop_all()
    _emergency = True
    bump()
    logger.warning(json.dumps({"event": "emergency_stop", "stopped": count}))
    return JSONResponse(status_code=200, content={"stopped": count})


def journal_entries() -> list[dict]:
    items = []
    for run in manager.recent(limit=200):
        d = run.to_dict()
        intensity = next((d["params"][k] for k in ("concurrency", "rate_per_s") if k in d["params"]), None)
        items.append({"run_id": d["run_id"], "scenario_id": d["scenario_id"], "type": SCENARIO_TO_LABEL.get(d["scenario_id"], "attack"),
                      "status": d["status"], "started_at": d["started_at"], "ended_at": d["ended_at"], "duration_s": d["elapsed_s"],
                      "intensity": intensity, "requests_sent": d["requests_sent"], "blocked": d["blocked"], "result": d["error"] or d["status"]})
    return items


@app.get("/api/journal")
def api_journal() -> dict:
    return {"items": journal_entries()}


@app.get("/api/journal.csv")
def api_journal_csv() -> PlainTextResponse:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["run_id", "scenario_id", "type", "status", "started_at", "ended_at",
                                                "duration_s", "intensity", "requests_sent", "blocked", "result"])
    writer.writeheader()
    for entry in journal_entries():
        writer.writerow(entry)
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=journal-attaques-poupal.csv"})


@app.get("/api/events")
async def api_events() -> StreamingResponse:
    async def stream():
        last, last_sent = -1, 0.0
        while True:
            now = asyncio.get_event_loop().time()
            if _version != last or now - last_sent >= 2.0:
                last, last_sent = _version, now
                yield f"event: state\ndata: {json.dumps(build_state(), ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.4)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready")
def ready() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "ok", "in_lab": in_lab})
