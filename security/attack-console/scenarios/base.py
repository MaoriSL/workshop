"""
Base commune des scénarios d'attaque (fictifs, confinés, reproductibles).

Un scénario décrit : son type d'incident attendu, la défense attendue, ses paramètres BORNÉS,
et une coroutine `run()` qui produit la charge. Intensité et durée sont plafonnées ici (pas de
saturation du PC Hôte), l'arrêt est immédiat (événement `stop`), rien ne persiste après l'arrêt.
"""
from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

import httpx

# Plafonds durs : même si l'interface envoyait une valeur plus grande, on la ramène ici.
MAX_DURATION_S = 180
MAX_CONCURRENCY = 100
MAX_RATE_PER_S = 100


@dataclass
class ParamField:
    key: str
    label: str
    type: Literal["int", "float", "select"]
    default: object
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[dict] | None = None
    unit: str | None = None

    def to_dict(self) -> dict:
        d = {"key": self.key, "label": self.label, "type": self.type, "default": self.default}
        for k in ("min", "max", "step", "options", "unit"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d


class RunCounters:
    """Compteurs d'une exécution, lus en direct par l'API (un seul event loop : pas de verrou)."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self.requests_sent = 0
        self.responses_by_status: Counter[str] = Counter()
        self.blocked = 0          # réponses 403 (WAF) ou 429 (rate limit)
        self.errors = 0

    def record(self, status: int | None) -> None:
        self.requests_sent += 1
        if status is None:
            self.errors += 1
            self.responses_by_status["erreur"] += 1
            return
        self.responses_by_status[str(status)] += 1
        if status in (403, 429):
            self.blocked += 1

    def snapshot(self) -> dict:
        elapsed = max(time.time() - self.started_at, 1e-6)
        return {
            "requests_sent": self.requests_sent,
            "responses_by_status": dict(self.responses_by_status),
            "blocked": self.blocked,
            "errors": self.errors,
            "rate_per_s": round(self.requests_sent / elapsed, 1),
        }


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    incident_type: str
    defense: str
    params: list[ParamField] = field(default_factory=list)

    def clamp(self, raw: dict) -> dict:
        """Valide et BORNE les paramètres reçus de l'interface (jamais de valeur arbitraire)."""
        out: dict = {}
        for field_ in self.params:
            value = raw.get(field_.key, field_.default)
            if field_.type == "select":
                allowed = [o["value"] for o in (field_.options or [])]
                out[field_.key] = value if value in allowed else field_.default
            else:
                try:
                    value = float(value) if field_.type == "float" else int(float(value))
                except (TypeError, ValueError):
                    value = field_.default
                if field_.min is not None:
                    value = max(field_.min, value)
                if field_.max is not None:
                    value = min(field_.max, value)
                out[field_.key] = value
        return out

    async def run(self, client: httpx.AsyncClient, params: dict, counters: RunCounters, stop: asyncio.Event) -> None:
        raise NotImplementedError

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description, "incident_type": self.incident_type,
                "defense": self.defense, "params_schema": [p.to_dict() for p in self.params]}


async def interruptible_sleep(seconds: float, stop: asyncio.Event) -> None:
    """Dort `seconds`, mais rend la main tout de suite si l'arrêt est demandé."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(0.0, seconds))
    except asyncio.TimeoutError:
        pass


async def send(client: httpx.AsyncClient, counters: RunCounters, method: str, path: str, **kw) -> httpx.Response | None:
    """Une requête vers la cible ; enregistre le code (ou l'erreur) dans les compteurs."""
    try:
        response = await client.request(method, path, **kw)
        counters.record(response.status_code)
        return response
    except httpx.HTTPError:
        counters.record(None)
        return None
