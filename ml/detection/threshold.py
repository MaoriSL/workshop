"""
Choix du seuil et simulation des alertes.

Le seuil n'est pas choisi "à l'œil" : on rejoue la machine à états du service temps réel sur
une période NORMALE mise de côté (jamais vue à l'entraînement) et on retient le seuil le plus
bas qui produit moins de `target` fausses alertes par heure. Plus le seuil est bas, plus le
détecteur est sensible (délai de détection court) mais plus il y a de fausses alertes :
c'est le compromis documenté dans REPORT.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .service.state_machine import ANOMALY, NORMAL, StateMachine


def simulate_alerts(scores: np.ndarray, threshold: float, confirm_n: int = 2, confirm_m: int = 3, recover_r: int = 6) -> list[tuple[int, int]]:
    """Rejoue la machine à états ; renvoie les épisodes d'ANOMALIE sous forme (index début, index fin)."""
    machine = StateMachine(confirm_n=confirm_n, confirm_m=confirm_m, recover_r=recover_r)
    episodes: list[tuple[int, int]] = []
    start: int | None = None
    for i, value in enumerate(scores):
        transition = machine.update(bool(value > threshold))
        if transition and transition.current == ANOMALY and start is None:
            start = i
        if transition and transition.current == NORMAL and start is not None:
            episodes.append((start, i))
            start = None
    if start is not None:
        episodes.append((start, len(scores) - 1))
    return episodes


def false_alerts_per_hour(scores: np.ndarray, threshold: float, step_seconds: float, **machine_kwargs) -> float:
    hours = max(len(scores) * step_seconds / 3600.0, 1e-9)
    return len(simulate_alerts(scores, threshold, **machine_kwargs)) / hours


def choose_threshold(holdout_scores: np.ndarray, step_seconds: float, target_per_hour: float = 1.0,
                     quantiles: tuple[float, ...] = (0.90, 0.95, 0.975, 0.99, 0.995, 0.999, 0.9999), **machine_kwargs) -> tuple[float, list[dict]]:
    """
    Essaie des seuils croissants (quantiles des scores normaux) et garde le plus bas qui respecte
    la cible de fausses alertes. Renvoie (seuil, courbe seuil → fausses alertes/h) pour le rapport.
    """
    curve: list[dict] = []
    chosen: float | None = None
    for q in quantiles:
        threshold = float(np.quantile(holdout_scores, q))
        rate = false_alerts_per_hour(holdout_scores, threshold, step_seconds, **machine_kwargs)
        curve.append({"quantile": q, "threshold": round(threshold, 6), "false_alerts_per_hour": round(rate, 3)})
        if chosen is None and rate <= target_per_hour:
            chosen = threshold
    if chosen is None:
        # Même le quantile le plus haut déclenche trop : marge de sécurité au-dessus du maximum observé
        chosen = float(holdout_scores.max()) * 1.05 + 1e-6
    return chosen, curve


def detection_delay(scores: pd.Series, threshold: float, start: pd.Timestamp, end: pd.Timestamp, **machine_kwargs) -> dict:
    """
    Pour une période étiquetée [start, end] : la machine à états, rejouée depuis 10 min avant le
    début, passe-t-elle en ANOMALIE pendant la période ? Au bout de combien de secondes ?
    """
    window = scores[(scores.index >= start - pd.Timedelta(minutes=10)) & (scores.index <= end + pd.Timedelta(minutes=2))]
    episodes = simulate_alerts(window.to_numpy(), threshold, **machine_kwargs)
    for first, _ in episodes:
        at = window.index[first]
        if start <= at <= end + pd.Timedelta(minutes=2):
            return {"detected": True, "delay_s": round((at - start).total_seconds(), 1), "alert_at": at.isoformat()}
    return {"detected": False, "delay_s": None, "alert_at": None}
