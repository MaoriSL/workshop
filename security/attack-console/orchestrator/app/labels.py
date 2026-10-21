"""
Étiquetage automatique : à chaque attaque, on écrit sa fenêtre (start, end, type, description)
dans ml/data/labels.csv. Les attaques deviennent ainsi des données ÉTIQUETÉES pour évaluer et
réentraîner le modèle de détection — c'est le lien direct avec le pilier IA.

Le type écrit est l'un de ceux que reconnaît ml/detection (overload, bruteforce, attack), pour
que l'évaluation (`python -m ml.detection.evaluate`) les prenne en compte sans rien changer.
"""
from __future__ import annotations

import csv
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

LABELS_PATH = Path(os.environ.get("LABELS_PATH", "/labels/labels.csv"))
_lock = threading.Lock()

# Scénario de la console → type reconnu par ml/data/labels.csv
SCENARIO_TO_LABEL = {"dos": "overload", "bruteforce": "bruteforce", "injection": "attack", "exfiltration": "attack", "combo": "attack"}


def iso(ts: datetime | None = None) -> str:
    return (ts or datetime.now(timezone.utc)).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_label(scenario_id: str, start: str, end: str, description: str) -> bool:
    """Ajoute une ligne à labels.csv (créé avec son en-tête si absent). Échec silencieux si le chemin n'est pas monté."""
    label_type = SCENARIO_TO_LABEL.get(scenario_id, "attack")
    try:
        with _lock:
            new_file = not LABELS_PATH.exists()
            LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LABELS_PATH.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                if new_file:
                    writer.writerow(["start", "end", "type", "description"])
                writer.writerow([start, end, label_type, description])
        return True
    except OSError:
        return False
