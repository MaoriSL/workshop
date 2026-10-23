"""
Modèle de détection : Isolation Forest (non supervisé, entraîné sur le NORMAL uniquement)
+ explication des alertes (variables les plus anormales, service suspecté, type d'incident).

Un seul objet `DetectionModel` est sauvegardé (joblib) et rechargé par le service temps réel.
Score d'anomalie = -decision_function : plus il est haut, plus le point est anormal.
La référence simple (`RobustZModel`) sert de comparaison dans le rapport.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from .features import service_of

INCIDENT_TYPES = ("indisponibilite", "surcharge", "bruteforce", "db_lente", "inconnu")
# Correspondance avec les types des scénarios étiquetés (labels.csv)
SCENARIO_TO_TYPE = {"outage": "indisponibilite", "overload": "surcharge", "bruteforce": "bruteforce", "db_slow": "db_lente"}


@dataclass
class Baseline:
    """Valeur habituelle (médiane) et dispersion (MAD) de chaque variable, calculées sur le normal."""
    median: pd.Series
    mad: pd.Series

    def zscores(self, row: pd.Series) -> pd.Series:
        """Écart robuste : (valeur - médiane) / (1,4826 × MAD), borné pour rester lisible."""
        scale = (1.4826 * self.mad).clip(lower=1e-9)
        z = (row - self.median) / scale
        # Variable constante à l'entraînement (MAD = 0) : tout écart est déjà "grand", on le borne
        z = z.where(self.mad > 0, np.sign(row - self.median) * np.minimum(np.abs(row - self.median) / (self.median.abs() + 1e-9), 1.0) * 10.0)
        return z.clip(-50, 50)


CLIP = 50.0


def fit_robust_scaler(x: np.ndarray) -> RobustScaler:
    """
    RobustScaler (médiane / écart interquartile) avec un PLANCHER sur l'échelle : une variable qui ne
    bouge jamais en fonctionnement normal (disponibilité = 1, taux de 5xx = 0, échecs de connexion = 0)
    aurait une échelle de 1 et sa chute ou sa hausse passerait inaperçue parmi 150 dimensions.
    Avec le plancher (2 % de la médiane, sinon 1e-3), tout écart sur une telle variable devient extrême,
    ce que l'Isolation Forest isole en quelques coupes.
    """
    scaler = RobustScaler().fit(x)
    q75, q25 = np.percentile(x, [75, 25], axis=0)
    p995, p005 = np.percentile(x, [99.5, 0.5], axis=0)
    # Plancher : 2 % de la médiane, ou un dixième de l'étendue normale (hors extrêmes), au minimum 1e-3
    floor = np.maximum.reduce([0.02 * np.abs(scaler.center_), (p995 - p005) / 10.0, np.full(x.shape[1], 1e-3)])
    # sklearn met l'échelle à 1 quand l'écart interquartile est nul : on la remplace par le plancher
    scaler.scale_ = np.where((q75 - q25) > 0, scaler.scale_, floor)
    return scaler


# Variables « signal de panne » : constantes en fonctionnement normal, tout écart est significatif.
# (Les variantes glissantes __diff/__mean/__std et les latences sont exclues : elles fluctuent naturellement.)
BREACH_PREFIXES = ("service_up__", "http_error_ratio_5xx_rate1m__", "db_errors_per_minute__", "container_restarts_total__",
                   "login_failures_per_minute__", "siem_", "ratio_failed_transactions", "ratio_5xx_total")


def constant_features(x: np.ndarray, names: list[str]) -> np.ndarray:
    """Masque des variables de panne sans dispersion interquartile à l'entraînement (voir BREACH_PREFIXES)."""
    q75, q25 = np.percentile(x, [75, 25], axis=0)
    curated = np.array([n.startswith(BREACH_PREFIXES) and not n.endswith(("__diff",)) and "__mean" not in n and "__std" not in n for n in names])
    return ((q75 - q25) <= 0) & curated


def scale_clipped(scaler: RobustScaler, x: np.ndarray) -> np.ndarray:
    """Normalisation puis bornage à ±CLIP (évite des valeurs infinies, garde l'ordre de grandeur)."""
    return np.clip(scaler.transform(x), -CLIP, CLIP)


class RobustZModel:
    """Référence simple : score = plus grand |z robuste| parmi les variables (sans apprentissage de structure)."""

    def __init__(self, baseline: Baseline) -> None:
        self.baseline = baseline

    def score(self, features: pd.DataFrame) -> np.ndarray:
        return np.array([self.baseline.zscores(row).abs().max() for _, row in features.iterrows()])


@dataclass
class DetectionModel:
    version: str
    feature_names: list[str]
    window: int
    scaler: RobustScaler
    forest: IsolationForest
    baseline: Baseline
    threshold: float = 0.0
    per_service: dict[str, tuple[list[str], RobustScaler, IsolationForest]] = field(default_factory=dict)
    type_classifier: object | None = None          # RandomForest facultatif (voir train.py)
    type_classifier_features: list[str] = field(default_factory=list)
    # Variables constantes à l'entraînement : une forêt ne peut pas les couper (aucune étendue),
    # donc elle ne voit pas leur écart. Leur « franchissement » est ajouté explicitement au score.
    constant_mask: np.ndarray | None = None
    breach_weight: float = 1.0

    # ---- scores ----
    def score(self, features: pd.DataFrame) -> np.ndarray:
        """
        Score global = maximum entre la forêt globale et les forêts par service.
        Une forêt sur 150 variables isole mal un écart porté par une seule variable (disponibilité,
        échecs de connexion...) ; les forêts par service, sur 15 à 40 variables, le voient nettement.
        """
        x = scale_clipped(self.scaler, features[self.feature_names].to_numpy(dtype=float))
        scores = [-self.forest.decision_function(x)]
        scores.extend(self.service_scores(features).values())
        score = np.max(np.vstack(scores), axis=0)
        if self.constant_mask is not None and self.constant_mask.any():
            breach = np.abs(x[:, self.constant_mask]).max(axis=1) / CLIP      # 0 (normal) → 1 (écart extrême)
            score = score + self.breach_weight * breach
        return score

    def service_scores(self, features: pd.DataFrame) -> dict[str, np.ndarray]:
        """Score par service (modèles entraînés sur le sous-ensemble de variables de chaque service)."""
        result = {}
        for service, (columns, scaler, forest) in self.per_service.items():
            x = scale_clipped(scaler, features[columns].to_numpy(dtype=float))
            result[service] = -forest.decision_function(x)
        return result

    # ---- explication ----
    def explain(self, row: pd.Series, top: int = 3) -> dict:
        """Service suspecté, 3 variables les plus anormales et type d'incident, pour un pas de temps."""
        scaled = scale_clipped(self.scaler, row[self.feature_names].to_numpy(dtype=float).reshape(1, -1))[0]
        z = pd.Series(scaled, index=self.feature_names)          # même normalisation que le score
        ranked = z.abs().sort_values(ascending=False)
        top_features = [
            {"name": name, "value": float(row[name]), "baseline": float(self.baseline.median[name]), "deviation": float(z[name])}
            for name in ranked.index[:top]
        ]
        # Attribution à un service : chaque métrique de base vote une seule fois (son plus grand écart,
        # toutes variantes glissantes confondues) ; un service tombé (service_up) ou un trafic disparu
        # pèse davantage qu'une baisse de CPU induite ailleurs par la panne.
        by_base: dict[str, float] = {}
        for name in ranked.index:
            by_base[base_metric(name)] = max(by_base.get(base_metric(name), 0.0), float(ranked[name]))
        by_service: dict[str, float] = {}
        for name, deviation in sorted(by_base.items(), key=lambda kv: -kv[1])[:10]:
            service = service_of(name)
            if service:
                by_service[service] = by_service.get(service, 0.0) + deviation * vote_weight(name)
        suspected = max(by_service, key=by_service.get) if by_service else "inconnu"
        incident_type = self.classify_type(row, z)
        return {"suspected_service": suspected, "top_features": top_features, "incident_type": incident_type,
                "service_votes": {k: round(v, 2) for k, v in sorted(by_service.items(), key=lambda kv: -kv[1])}}

    def classify_type(self, row: pd.Series, z: pd.Series) -> str:
        if self.type_classifier is not None:
            x = row.reindex(self.type_classifier_features, fill_value=0.0).to_numpy(dtype=float).reshape(1, -1)
            return str(self.type_classifier.predict(x)[0])
        return rule_based_type(row, z)


def base_metric(feature: str) -> str:
    """'http_latency_seconds_p95__poupal-api__mean12' -> 'http_latency_seconds_p95__poupal-api'."""
    for suffix in ("__diff",):
        if feature.endswith(suffix):
            return feature[: -len(suffix)]
    parts = feature.rsplit("__", 1)
    if len(parts) == 2 and (parts[1].startswith("mean") or parts[1].startswith("std")):
        return parts[0]
    return feature


def vote_weight(feature: str) -> float:
    """Poids d'une métrique dans l'attribution du service suspecté."""
    if feature.startswith("service_up__"):
        return 4.0
    if feature.startswith(("http_requests_per_second", "http_error_ratio_5xx", "http_latency_seconds_p95", "login_failures", "db_connections_active")):
        return 2.0
    if feature.startswith("container_cpu"):
        return 0.5
    return 1.0


def rule_based_type(row: pd.Series, z: pd.Series) -> str:
    """Type d'incident déduit des variables les plus anormales (utilisé si pas assez d'exemples étiquetés)."""
    if row.get("siem_waf_block_sources", 0.0) > 0:
        return "injection"
    if row.get("siem_enumeration_sources", 0.0) > 0:
        return "exfiltration"
    if row.get("siem_bruteforce_sources", 0.0) > 0:
        return "bruteforce"
    if row.get("siem_rate_limited_sources", 0.0) > 0:
        return "surcharge"

    def total(prefix: str, signed: bool = True) -> float:
        cols = [c for c in z.index if c.startswith(prefix) and "__mean" not in c and "__std" not in c and "__diff" not in c]
        values = z[cols] if cols else pd.Series(dtype=float)
        return float(values.sum()) if signed else float(values.abs().sum())

    # Disponibilité : uniquement les colonnes brutes service_up__<job> (pas les variantes __diff/__mean)
    down = [c for c in z.index if c.startswith("service_up__") and "__" not in c[len("service_up__"):] and row[c] < 0.5]
    if down or total("http_requests_per_second_rate1m") < -6 and total("http_error_ratio_5xx_rate1m") > 3:
        return "indisponibilite"
    if total("login_failures_per_minute") > 4:
        return "bruteforce"
    if total("db_connections_active") > 4 or (total("http_latency_seconds_p95") > 4 and total("http_requests_per_second_rate1m") <= 2):
        return "db_lente"
    if total("http_requests_per_second_rate1m") > 4 or total("gateway_requests_per_second_rate1m") > 4 or total("container_cpu_cores_rate1m") > 4:
        return "surcharge"
    if total("http_error_ratio_5xx_rate1m") > 3:
        return "indisponibilite"
    return "inconnu"
