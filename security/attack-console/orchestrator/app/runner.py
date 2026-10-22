"""
Superviseur d'exécution : démarre, borne et arrête les scénarios.

Garanties : un seul run par scénario à la fois ; durée bornée (le superviseur arme un arrêt
automatique) ; arrêt immédiat (stop-all) qui coupe toutes les tâches ; après l'arrêt, plus
aucune charge. L'orchestrateur n'exécute QUE les scénarios de la liste blanche `scenarios/`.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

import httpx

import sys
sys.path.insert(0, "/app")   # racine du conteneur : accès au paquet scenarios
from scenarios import SCENARIOS  # noqa: E402
from scenarios.base import MAX_DURATION_S, RunCounters  # noqa: E402

from .labels import append_label, iso  # noqa: E402


class Run:
    def __init__(self, scenario_id: str, params: dict, target: str) -> None:
        self.run_id = f"run-{datetime.now(timezone.utc).strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
        self.scenario_id = scenario_id
        self.params = params
        self.target = target
        self.status = "running"
        self.counters = RunCounters()
        self.started_at = iso()
        self.started_monotonic = time.monotonic()
        self.ended_at: str | None = None
        self.error: str | None = None
        self.stop = asyncio.Event()
        self.task: asyncio.Task | None = None
        self._label_start = self.started_at

    def elapsed_s(self) -> float:
        end = self.started_monotonic if self.status != "running" else time.monotonic()
        return round((time.monotonic() if self.status == "running" else end) - self.started_monotonic, 1)

    def to_dict(self) -> dict:
        snap = self.counters.snapshot()
        return {"run_id": self.run_id, "scenario_id": self.scenario_id, "status": self.status, "params": self.params,
                "started_at": self.started_at, "ended_at": self.ended_at, "elapsed_s": self.elapsed_s(),
                "error": self.error, **snap}


class RunManager:
    def __init__(self, target: str) -> None:
        self.target = target
        self.runs: dict[str, Run] = {}
        self.order: list[str] = []
        self.on_change = lambda: None

    def active(self, scenario_id: str) -> Run | None:
        for run in self.runs.values():
            if run.scenario_id == scenario_id and run.status == "running":
                return run
        return None

    def any_active(self) -> bool:
        return any(run.status == "running" for run in self.runs.values())

    def set_target(self, target: str) -> None:
        if self.any_active():
            raise RuntimeError("Impossible de modifier la cible pendant une attaque.")
        self.target = target

    def recent(self, limit: int = 30) -> list[Run]:
        return [self.runs[r] for r in reversed(self.order)][:limit]

    def start(self, scenario_id: str, raw_params: dict) -> Run:
        scenario = SCENARIOS[scenario_id]
        params = scenario.clamp(raw_params)
        run = Run(scenario_id, params, self.target)
        self.runs[run.run_id] = run
        self.order.append(run.run_id)
        run.task = asyncio.create_task(self._supervise(scenario, run))
        self.on_change()
        return run

    async def _supervise(self, scenario, run: Run) -> None:
        duration = min(int(run.params.get("duration_s", run.params.get("attack_s", 60))) +
                       int(run.params.get("recon_s", 0)), MAX_DURATION_S)
        # Borne de sécurité : l'arrêt automatique est armé quoi qu'il arrive
        timer = asyncio.create_task(self._auto_stop(run, duration))
        headers = {"User-Agent": "poupal-attack-console/0.1 (laboratoire)"}
        try:
            async with httpx.AsyncClient(base_url=self.target, timeout=10.0, headers=headers, verify=False) as client:
                await scenario.run(client, run.params, run.counters, run.stop)
            if run.status == "running":
                run.status = "finished"
        except asyncio.CancelledError:
            run.status = "stopped"
            raise
        except Exception as exc:   # un scénario qui plante ne doit pas tuer l'orchestrateur
            run.status = "error"
            run.error = f"{type(exc).__name__}: {exc}"[:200]
        finally:
            timer.cancel()
            run.ended_at = iso()
            append_label(run.scenario_id, run._label_start, run.ended_at,
                         f"{scenario.name} (console ; {self._intensity_str(run)})")
            self.on_change()

    async def _auto_stop(self, run: Run, duration: int) -> None:
        try:
            await asyncio.sleep(duration)
            run.stop.set()
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _intensity_str(run: Run) -> str:
        for key in ("concurrency", "rate_per_s"):
            if key in run.params:
                return f"{key}={run.params[key]}"
        return "intensité par défaut"

    def stop(self, scenario_id: str) -> bool:
        run = self.active(scenario_id)
        if run is None:
            return False
        run.status = "stopped"
        run.stop.set()
        self.on_change()
        return True

    def stop_all(self) -> int:
        count = 0
        for run in self.runs.values():
            if run.status == "running":
                run.status = "stopped"
                run.stop.set()
                count += 1
        self.on_change()
        return count
