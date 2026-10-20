"""
Cycle de vie d'un incident, historique et garde-fous.

    RECU → DECIDE → ACTION_EN_COURS → VERIFICATION → RETABLI
                                   ↘ ESCALADE (niveau suivant) … → ECHEC (après 3 actions)

Garde-fous : 3 actions maximum par incident ; délai minimum entre deux actions ; disjoncteur
(trop de remédiations sur une fenêtre glissante → état SURETE, on cesse d'agir et on signale).
Module pur (aucune E/S) : testé unitairement.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

RECU, DECIDE, ACTION_EN_COURS, VERIFICATION, RETABLI, ESCALADE, ECHEC = (
    "RECU", "DECIDE", "ACTION_EN_COURS", "VERIFICATION", "RETABLI", "ESCALADE", "ECHEC")
TERMINAL = {RETABLI, ECHEC}

MAX_ACTIONS_PER_INCIDENT = 3


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Step:
    t: datetime
    elapsed_s: float
    step: str
    label: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"t": self.t.isoformat(timespec="milliseconds"), "elapsed_s": self.elapsed_s, "step": self.step, "label": self.label, "details": self.details}


@dataclass
class Incident:
    incident_id: str
    incident_type: str
    suspected_service: str
    detected_at: datetime
    received_at: datetime
    score: float | None = None
    threshold: float | None = None
    top_features: list = field(default_factory=list)
    state: str = RECU
    plan: list[dict] = field(default_factory=list)
    current_level: int = 0
    actions_done: int = 0
    timeline: list[Step] = field(default_factory=list)
    proof: dict | None = None
    resolved_at: datetime | None = None
    recovery_seconds: float | None = None
    failure_reason: str | None = None
    detector_normal_at: datetime | None = None

    def add_step(self, step: str, label: str, **details) -> Step:
        t = now()
        entry = Step(t=t, elapsed_s=round((t - self.detected_at).total_seconds(), 1), step=step, label=label, details=details)
        self.timeline.append(entry)
        return entry

    def set_state(self, state: str) -> None:
        self.state = state

    def finish_recovered(self, proof: dict) -> None:
        self.proof = proof
        self.resolved_at = now()
        self.recovery_seconds = round((self.resolved_at - self.detected_at).total_seconds(), 1)
        self.state = RETABLI

    def finish_failed(self, reason: str) -> None:
        self.failure_reason = reason
        self.resolved_at = now()
        self.state = ECHEC

    @property
    def is_open(self) -> bool:
        return self.state not in TERMINAL

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id, "state": self.state, "incident_type": self.incident_type,
            "suspected_service": self.suspected_service, "score": self.score, "threshold": self.threshold,
            "detected_at": self.detected_at.isoformat(timespec="milliseconds"),
            "received_at": self.received_at.isoformat(timespec="milliseconds"),
            "resolved_at": self.resolved_at.isoformat(timespec="milliseconds") if self.resolved_at else None,
            "recovery_seconds": self.recovery_seconds, "plan": self.plan, "current_level": self.current_level,
            "actions_done": self.actions_done, "timeline": [s.to_dict() for s in self.timeline], "proof": self.proof,
            "failure_reason": self.failure_reason, "top_features": self.top_features,
            "detector_normal_at": self.detector_normal_at.isoformat(timespec="seconds") if self.detector_normal_at else None,
        }


@dataclass
class CircuitBreaker:
    """Plus de `limit` actions en `window_minutes` → ouvert (mode SURETE)."""
    limit: int = 8
    window_minutes: int = 10
    _actions: deque = field(default_factory=deque)

    def record(self, at: datetime | None = None) -> None:
        self._actions.append(at or now())
        self._prune()

    def _prune(self) -> None:
        cutoff = now().timestamp() - self.window_minutes * 60
        while self._actions and self._actions[0].timestamp() < cutoff:
            self._actions.popleft()

    @property
    def count(self) -> int:
        self._prune()
        return len(self._actions)

    @property
    def open(self) -> bool:
        return self.count >= self.limit

    def to_dict(self) -> dict:
        return {"open": self.open, "count": self.count, "limit": self.limit, "window_minutes": self.window_minutes}


class Registry:
    """Incidents connus (idempotence sur incident_id) et incident ouvert par service."""

    def __init__(self, max_history: int = 200) -> None:
        self.incidents: dict[str, Incident] = {}
        self.order: deque[str] = deque(maxlen=max_history)

    def get(self, incident_id: str) -> Incident | None:
        return self.incidents.get(incident_id)

    def add(self, incident: Incident) -> None:
        self.incidents[incident.incident_id] = incident
        self.order.append(incident.incident_id)

    def open_for_service(self, service: str) -> Incident | None:
        for incident in self.incidents.values():
            if incident.is_open and incident.suspected_service == service:
                return incident
        return None

    def current(self) -> Incident | None:
        for incident_id in reversed(self.order):
            incident = self.incidents[incident_id]
            if incident.is_open:
                return incident
        return None

    def last(self) -> Incident | None:
        return self.incidents[self.order[-1]] if self.order else None

    def history(self) -> list[Incident]:
        return [self.incidents[i] for i in reversed(self.order)]
