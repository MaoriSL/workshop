"""
Chargement des données du détecteur : CSV historiques (ml/data/) et lecture en direct
dans Prometheus. Les deux produisent le MÊME tableau (index timestamp UTC, une colonne
par règle d'enregistrement nommée comme dans scripts/export_metrics.py).
Bibliothèque standard + pandas uniquement (le service temps réel reste léger).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

RULE_PREFIX = "poupal:"
# Label qui identifie la série d'une règle (dans cet ordre de priorité)
SERIES_LABELS = ("service", "container", "status", "job")


def column_name(rule: str, labels: dict[str, str]) -> str:
    """'poupal:http_latency_seconds:p95' + {service: poupal-api} → 'http_latency_seconds_p95__poupal-api'."""
    base = rule.removeprefix(RULE_PREFIX).replace(":", "_")
    for key in SERIES_LABELS:
        if labels.get(key):
            return f"{base}__{labels[key]}"
    return base


# ---------------------------------------------------------------- CSV (entraînement)
def load_csv_dir(data_dir: str | Path, pattern: str = "metrics-*.csv") -> pd.DataFrame:
    """Concatène tous les exports CSV, trie par temps, supprime les doublons de timestamp."""
    files = sorted(Path(data_dir).glob(pattern))
    if not files:
        raise FileNotFoundError(f"Aucun fichier {pattern} dans {data_dir}")
    frames = [pd.read_csv(f, parse_dates=["timestamp"], index_col="timestamp") for f in files]
    frame = pd.concat(frames).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame


def load_labels(path: str | Path) -> pd.DataFrame:
    """labels.csv : start, end (ISO 8601), type, description. Vide si le fichier est absent."""
    path = Path(path)
    if not path.is_file():
        return pd.DataFrame(columns=["start", "end", "type", "description"])
    labels = pd.read_csv(path, parse_dates=["start", "end"])
    for col in ("start", "end"):
        if labels[col].dt.tz is None:
            labels[col] = labels[col].dt.tz_localize("UTC")
    return labels


def mask_labeled(index: pd.DatetimeIndex, labels: pd.DataFrame, margin: timedelta = timedelta(seconds=60)) -> pd.Series:
    """True pour les pas de temps situés dans une période étiquetée (± marge de sécurité)."""
    mask = pd.Series(False, index=index)
    for _, row in labels.iterrows():
        mask |= (index >= row["start"] - margin) & (index <= row["end"] + margin)
    return mask


# ---------------------------------------------------------------- Prometheus (temps réel)
def _get_json(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode())


def list_recording_rules(prometheus_url: str, timeout: float = 5.0) -> list[str]:
    """Noms des règles d'enregistrement commençant par le préfixe."""
    payload = _get_json(f"{prometheus_url.rstrip('/')}/api/v1/rules?type=record", timeout)
    names: list[str] = []
    for group in payload.get("data", {}).get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("type") == "recording" and rule["name"].startswith(RULE_PREFIX):
                names.append(rule["name"])
    return sorted(set(names))


def fetch_range(prometheus_url: str, rules: list[str], start: datetime, end: datetime,
                step_seconds: int = 5, timeout: float = 5.0) -> pd.DataFrame:
    """query_range sur chaque règle → tableau index timestamp, une colonne par série."""
    base = prometheus_url.rstrip("/")
    columns: dict[str, dict[pd.Timestamp, float]] = {}
    for rule in rules:
        query = urllib.parse.urlencode({"query": rule, "start": start.timestamp(), "end": end.timestamp(), "step": step_seconds})
        payload = _get_json(f"{base}/api/v1/query_range?{query}", timeout)
        for series in payload.get("data", {}).get("result", []):
            name = column_name(rule, series.get("metric", {}))
            points = columns.setdefault(name, {})
            for ts, value in series.get("values", []):
                points[pd.Timestamp(float(ts), unit="s", tz="UTC")] = float(value)
    frame = pd.DataFrame(columns)
    if frame.empty:
        return frame
    return frame.sort_index()


def fetch_recent(prometheus_url: str, rules: list[str], minutes: float = 3.0, step_seconds: int = 5, timeout: float = 5.0) -> pd.DataFrame:
    """Les dernières `minutes` de données (pour le calcul temps réel des variables)."""
    end = datetime.now(timezone.utc)
    return fetch_range(prometheus_url, rules, end - timedelta(minutes=minutes), end, step_seconds, timeout)
