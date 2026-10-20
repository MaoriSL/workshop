"""
Limiteur de débit simple, en mémoire (fenêtre glissante par clé : IP ou utilisateur).

Suffisant pour un service à une seule instance (cas du démonstrateur). Pour plusieurs
instances, le même algorithme se transpose dans Redis sans changer les appelants.
"""
from __future__ import annotations

import threading
import time
from collections import deque


def parse_limit(spec: str) -> tuple[int, int]:
    """"5/60" → (5 requêtes, 60 secondes)."""
    count, window = spec.split("/")
    return int(count), int(window)


class RateLimiter:
    def __init__(self, spec: str) -> None:
        self.limit, self.window = parse_limit(spec)
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        """
        Enregistre une tentative pour `key` et indique si elle est autorisée.
        Retourne (autorisé, secondes à attendre avant la prochaine tentative).
        """
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            # On oublie les tentatives sorties de la fenêtre
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = int(self.window - (now - hits[0])) + 1
                return False, retry_after
            hits.append(now)
            return True, 0

    def reset(self) -> None:
        """Vide le compteur (utilisé par les tests)."""
        with self._lock:
            self._hits.clear()
