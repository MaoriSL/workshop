"""
Machine à états du détecteur : évite les fausses alertes sur un pic isolé.

    NORMAL ──(score > seuil)──► SUSPECT ──(N dépassements sur M fenêtres)──► ANOMALIE
       ▲                                                                       │
       └──(score < seuil pendant R fenêtres)── RÉTABLISSEMENT ◄──(score < seuil)┘

N, M et R sont paramétrables (variables DETECTOR_CONFIRM_N, DETECTOR_CONFIRM_M, DETECTOR_RECOVER_R).
Pure logique, sans dépendance : testée unitairement.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

NORMAL = "NORMAL"
SUSPECT = "SUSPECT"
ANOMALY = "ANOMALIE"
RECOVERING = "RETABLISSEMENT"


@dataclass
class Transition:
    previous: str
    current: str
    at: datetime


@dataclass
class StateMachine:
    confirm_n: int = 2       # dépassements nécessaires...
    confirm_m: int = 3       # ...parmi les M dernières fenêtres pour confirmer une anomalie
    recover_r: int = 6       # fenêtres consécutives sous le seuil pour revenir à NORMAL
    state: str = NORMAL
    since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _recent: deque = field(default_factory=deque)   # True = au-dessus du seuil
    _below_streak: int = 0

    def __post_init__(self) -> None:
        self._recent = deque(maxlen=self.confirm_m)

    def update(self, above_threshold: bool, now: datetime | None = None) -> Transition | None:
        """Nouvelle fenêtre (toutes les 5 s). Renvoie la transition s'il y en a une."""
        now = now or datetime.now(timezone.utc)
        self._recent.append(above_threshold)
        self._below_streak = 0 if above_threshold else self._below_streak + 1
        exceed = sum(self._recent)
        previous = self.state

        if self.state == NORMAL:
            if above_threshold:
                self.state = SUSPECT
        elif self.state == SUSPECT:
            if exceed >= self.confirm_n:
                self.state = ANOMALY
            elif exceed == 0:
                self.state = NORMAL
        elif self.state == ANOMALY:
            if not above_threshold:
                self.state = RECOVERING
        elif self.state == RECOVERING:
            if above_threshold:
                self.state = ANOMALY          # rechute : l'incident continue
            elif self._below_streak >= self.recover_r:
                self.state = NORMAL

        if self.state != previous:
            self.since = now
            return Transition(previous, self.state, now)
        return None
