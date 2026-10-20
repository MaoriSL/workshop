#!/usr/bin/env python3
"""
Évaluation du détecteur sur les périodes étiquetées (labels.csv) et sur le normal de réserve.

    python -m ml.detection.evaluate [--data-dir ml/data] [--model ml/detection/models] [--out ml/detection/reports]

Produit : reports/evaluation.json (détection, délai, type par scénario ; fausses alertes/heure),
          reports/anomaly_score.png (score dans le temps, seuil, périodes surlignées),
          reports/detection_delays.png (délais par scénario), reports/evaluation.md (tableau).
Relancer après chaque nouveau scénario (ou une attaque réelle ajoutée à labels.csv).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .data import load_csv_dir, load_labels, mask_labeled
from .features import build_features
from .model import SCENARIO_TO_TYPE, DetectionModel, RobustZModel
from .threshold import detection_delay, false_alerts_per_hour

COLORS = {"outage": "#dc2626", "overload": "#d97706", "bruteforce": "#7c3aed", "db_slow": "#0891b2", "attack": "#000000"}


def evaluate(args: argparse.Namespace) -> tuple[dict, pd.Series, pd.DataFrame, DetectionModel]:
    model: DetectionModel = joblib.load(Path(args.model) / "model.joblib")
    metadata = json.loads((Path(args.model) / "metadata.json").read_text(encoding="utf-8"))
    machine = metadata["state_machine"]
    step = float(metadata["step_seconds"])
    raw = load_csv_dir(args.data_dir).ffill().fillna(0.0)
    labels = load_labels(args.labels)
    labels = labels[labels["type"].isin(list(SCENARIO_TO_TYPE) + ["attack"])]
    labels = labels[(labels["start"] >= raw.index.min()) & (labels["end"] <= raw.index.max())]   # périodes couvertes par les données
    features = build_features(raw, window=model.window).reindex(columns=model.feature_names, fill_value=0.0)
    scores = pd.Series(model.score(features), index=features.index)
    reference = RobustZModel(model.baseline)
    ref_scores = pd.Series(reference.score(features), index=features.index)
    ref_threshold = metadata["reference_robust_z"]["threshold"]

    # --- scénarios : détecté ? délai ? type correct ?
    rows = []
    for _, label in labels.iterrows():
        result = detection_delay(scores, model.threshold, label["start"], label["end"], **machine)
        ref = detection_delay(ref_scores, ref_threshold, label["start"], label["end"], **machine)
        found_type, suspected = None, None
        if result["detected"]:
            explanation = model.explain(features.loc[pd.Timestamp(result["alert_at"])])
            found_type, suspected = explanation["incident_type"], explanation["suspected_service"]
        expected = SCENARIO_TO_TYPE.get(str(label["type"]), "attack")
        rows.append({"type": str(label["type"]), "description": str(label.get("description", "")), "start": label["start"].isoformat(),
                     "end": label["end"].isoformat(), "detected": result["detected"], "delay_s": result["delay_s"],
                     "suspected_service": suspected, "incident_type": found_type,
                     "type_correct": (found_type == expected) if found_type else None,
                     "reference_detected": ref["detected"], "reference_delay_s": ref["delay_s"]})

    # --- fausses alertes sur le normal de réserve (jamais vu à l'entraînement, hors périodes étiquetées)
    holdout_start = pd.Timestamp(metadata["holdout_period"]["start"])
    normal_mask = ~mask_labeled(scores.index, labels).to_numpy() & (scores.index >= holdout_start)
    fa = false_alerts_per_hour(scores[normal_mask].to_numpy(), model.threshold, step, **machine) if normal_mask.any() else None
    fa_ref = false_alerts_per_hour(ref_scores[normal_mask].to_numpy(), ref_threshold, step, **machine) if normal_mask.any() else None
    delays = [r["delay_s"] for r in rows if r["delay_s"] is not None]
    summary = {"model_version": model.version, "threshold": model.threshold, "scenarios": rows,
               "detected": sum(1 for r in rows if r["detected"]), "total": len(rows),
               "mean_delay_s": round(sum(delays) / len(delays), 1) if delays else None,
               "false_alerts_per_hour_holdout": fa,
               "reference": {"threshold": ref_threshold, "detected": sum(1 for r in rows if r["reference_detected"]), "false_alerts_per_hour_holdout": fa_ref}}
    return summary, scores, labels, model


def plot(summary: dict, scores: pd.Series, labels: pd.DataFrame, model: DetectionModel, out: Path) -> None:
    """Graphiques PNG pour le dossier d'ingénierie."""
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(scores.index, scores.values, lw=0.8, color="#1b3a8b", label="score d'anomalie (Isolation Forest)")
    ax.axhline(model.threshold, color="#dc2626", ls="--", label=f"seuil = {model.threshold:.3f}")
    for _, label in labels.iterrows():
        ax.axvspan(label["start"], label["end"], color=COLORS.get(str(label["type"]), "grey"), alpha=0.2, label=str(label["type"]))
    handles, names = ax.get_legend_handles_labels()
    unique = dict(zip(names, handles))
    ax.legend(unique.values(), unique.keys(), loc="upper left", fontsize=8)
    ax.set_title("Poupal - score d'anomalie dans le temps (périodes étiquetées surlignées)")
    ax.set_ylabel("score (plus haut = plus anormal)")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out / "anomaly_score.png", dpi=130)
    plt.close(fig)

    rows = summary["scenarios"]
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(9, 4))
    names = [f"{r['type']}\n{r['start'][11:16]}" for r in rows]
    heights = [r["delay_s"] if r["delay_s"] is not None else 0 for r in rows]
    colors = [COLORS.get(r["type"], "grey") if r["detected"] else "#9ca3af" for r in rows]
    bars = ax.bar(names, heights, color=colors)
    ax.axhline(30, color="#dc2626", ls="--", label="objectif : 30 s")
    for bar, r in zip(bars, rows):
        text = f"{r['delay_s']:.0f} s" if r["detected"] else "non détecté"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, text, ha="center", fontsize=8)
    ax.set_ylabel("délai de détection (s)")
    ax.set_title("Délai de détection par scénario")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "detection_delays.png", dpi=130)
    plt.close(fig)


def markdown_table(summary: dict) -> str:
    lines = ["| Scénario | Début (UTC) | Détecté | Délai | Service suspecté | Type trouvé | Type OK | Référence z (détecté / délai) |",
             "|---|---|---|---|---|---|---|---|"]
    for r in summary["scenarios"]:
        delay = f"{r['delay_s']} s" if r["delay_s"] is not None else "-"
        ref_delay = f"{r['reference_delay_s']} s" if r["reference_delay_s"] is not None else "-"
        type_ok = "-" if r["type_correct"] is None else ("oui" if r["type_correct"] else "non")
        lines.append(f"| {r['type']} | {r['start'][11:19]} | {'oui' if r['detected'] else 'non'} | {delay} | {r['suspected_service'] or '-'} | "
                     f"{r['incident_type'] or '-'} | {type_ok} | {'oui' if r['reference_detected'] else 'non'} / {ref_delay} |")
    fa, fa_ref = summary["false_alerts_per_hour_holdout"], summary["reference"]["false_alerts_per_hour_holdout"]
    lines.append("")
    lines.append(f"Fausses alertes / heure sur le normal de réserve : Isolation Forest = {'-' if fa is None else round(fa, 2)} ; "
                 f"référence z robuste = {'-' if fa_ref is None else round(fa_ref, 2)}.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Évalue le détecteur sur les scénarios étiquetés.")
    parser.add_argument("--data-dir", default="ml/data")
    parser.add_argument("--labels", default="ml/data/labels.csv")
    parser.add_argument("--model", default="ml/detection/models")
    parser.add_argument("--out", default="ml/detection/reports")
    args = parser.parse_args(argv)

    summary, scores, labels, model = evaluate(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    plot(summary, scores, labels, model, out)
    table = markdown_table(summary)
    (out / "evaluation.md").write_text(table, encoding="utf-8")
    print(table)
    print(f"évaluation : {summary['detected']}/{summary['total']} scénarios détectés, délai moyen {summary['mean_delay_s']} s, graphiques dans {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
