"""
Calcul des VARIABLES du détecteur d'anomalies Poupal.

UN SEUL module, utilisé à l'identique :
  - à l'entraînement (train.py / evaluate.py) sur l'historique exporté en CSV ;
  - en temps réel (service/) sur les dernières minutes lues dans Prometheus.
Même entrée (DataFrame indexé par timestamp, une colonne par règle Prometheus),
même sortie (DataFrame de variables) : aucune différence possible entre les deux.

Entrée attendue (colonnes produites par scripts/export_metrics.py et data.py) :
    <règle sans préfixe "poupal:", ":" → "_">__<valeur du label service|container|status|job>
    ex. http_requests_per_second_rate1m__poupal-api, container_memory_bytes__db,
        transactions_per_minute__completed, service_up__api
Sortie : pour chaque variable brute retenue, 4 colonnes (valeur, moyenne glissante,
écart-type glissant, variation) + quelques ratios métier. Tout est numérique, sans NaN.
"""
from __future__ import annotations

import pandas as pd

# Fenêtre glissante (en pas de temps). Pas de 5 s → 12 pas = 1 minute.
DEFAULT_WINDOW = 12

# Services suivis et préfixes de leurs variables : sert à attribuer une alerte à un service.
SERVICES: dict[str, list[str]] = {
    "poupal-auth": ["__poupal-auth", "__auth", "login_"],
    "poupal-api": ["__poupal-api", "__api", "transactions_", "transaction_"],
    "poupal-gateway": ["__poupal-gateway", "__gateway", "gateway_"],
    "poupal-db": ["__poupal-db", "__db", "db_"],
}

# Règles d'enregistrement retenues comme variables brutes (préfixe "poupal:" retiré, ":" → "_").
BASE_METRICS: tuple[str, ...] = (
    "http_requests_per_second_rate1m",
    "http_error_ratio_4xx_rate1m",
    "http_error_ratio_5xx_rate1m",
    "http_latency_seconds_p50",
    "http_latency_seconds_p95",
    "gateway_requests_per_second_rate1m",
    "gateway_active_connections",
    "login_failures_per_minute",
    "login_attempts_per_minute",
    "transactions_per_minute",
    "db_errors_per_minute",
    "db_connections_active",
    "db_connections_total",
    "db_transactions_per_second_rate1m",
    "container_cpu_cores_rate1m",
    "container_memory_bytes",
    "container_restarts_total",
    "service_up",
)

# Conteneurs dont CPU / mémoire / redémarrages sont suivis (les autres sont ignorés : bruit).
CONTAINERS: tuple[str, ...] = ("auth", "api", "db", "gateway")


def select_raw_columns(columns: list[str]) -> list[str]:
    """Garde les colonnes qui correspondent aux variables brutes retenues (ordre stable)."""
    selected: list[str] = []
    for column in sorted(columns):
        base, _, label = column.partition("__")
        if base not in BASE_METRICS:
            continue
        if base.startswith("container_") and label not in CONTAINERS:
            continue
        selected.append(column)
    return selected


def service_of(feature: str) -> str | None:
    """Service auquel rattacher une variable (ex. 'http_latency_seconds_p95__poupal-api' → poupal-api)."""
    base, _, label = feature.partition("__")
    for service, markers in SERVICES.items():
        for marker in markers:
            if marker.startswith("__") and label == marker[2:]:
                return service
            if not marker.startswith("__") and base.startswith(marker):
                return service
    return None


def build_features(raw: pd.DataFrame, window: int = DEFAULT_WINDOW) -> pd.DataFrame:
    """
    Transforme les variables brutes en variables du modèle.

    raw : DataFrame indexé par timestamp (croissant, pas régulier), colonnes = règles.
    Pour chaque colonne retenue c :
        c            valeur brute
        c__mean{w}   moyenne glissante sur `window` pas
        c__std{w}    écart-type glissant (0 au début)
        c__diff      variation par rapport au pas précédent (0 au début)
    Ratios métier ajoutés quand les colonnes existent :
        ratio_failed_transactions   échouées / (toutes)
        ratio_5xx_total             somme des taux 5xx des services
    Les trous (NaN) sont comblés par la dernière valeur connue, puis 0 : un service
    absent de Prometheus (arrêté) apparaît donc comme une chute brutale, ce qui est voulu.
    """
    if raw.index.has_duplicates:
        raw = raw[~raw.index.duplicated(keep="last")]
    raw = raw.sort_index()
    columns = select_raw_columns(list(raw.columns))
    base = raw[columns].astype("float64").ffill().fillna(0.0)

    parts: list[pd.DataFrame] = [base]
    rolling = base.rolling(window=window, min_periods=1)
    parts.append(rolling.mean().add_suffix(f"__mean{window}"))
    parts.append(rolling.std(ddof=0).fillna(0.0).add_suffix(f"__std{window}"))
    parts.append(base.diff().fillna(0.0).add_suffix("__diff"))

    ratios = pd.DataFrame(index=base.index)
    failed = base.get("transactions_per_minute__failed")
    completed = base.get("transactions_per_minute__completed")
    if failed is not None and completed is not None:
        total = failed + completed + base.get("transactions_per_minute__pending", 0.0)
        ratios["ratio_failed_transactions"] = (failed / total.clip(lower=1e-9)).where(total > 0, 0.0)
    error_cols = [c for c in columns if c.startswith("http_error_ratio_5xx_rate1m__")]
    if error_cols:
        ratios["ratio_5xx_total"] = base[error_cols].sum(axis=1)
    if not ratios.empty:
        parts.append(ratios)

    features = pd.concat(parts, axis=1)
    return features.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)


def align_features(features: pd.DataFrame, expected: list[str]) -> pd.DataFrame:
    """Aligne sur la liste de variables du modèle : colonnes manquantes → 0, colonnes en trop → ignorées."""
    return features.reindex(columns=expected, fill_value=0.0)


def latest_features(raw: pd.DataFrame, expected: list[str], window: int = DEFAULT_WINDOW) -> pd.Series:
    """Variables du DERNIER pas de temps (temps réel) : même calcul que l'entraînement."""
    features = align_features(build_features(raw, window=window), expected)
    return features.iloc[-1]
