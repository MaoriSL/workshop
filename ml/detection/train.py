#!/usr/bin/env python3
"""
Entraînement du détecteur d'anomalies Poupal.

    python -m ml.detection.train [--data-dir ml/data] [--out ml/detection/models] [--holdout 0.25]

Étapes :
  1. charge les CSV de ml/data, nettoie (doublons, trous, colonnes constantes signalées) ;
  2. exclut les périodes non normales de labels.csv (± 60 s) ;
  3. découpe chronologiquement le normal : entraînement (début) / réserve (fin, jamais vue) ;
  4. variables (features.py), RobustScaler ajusté sur l'entraînement SEULEMENT ;
  5. Isolation Forest global + un modèle par service ; référence « z robuste » ;
  6. seuil choisi sur la réserve : < 1 fausse alerte / heure (machine à états rejouée) ;
  7. type d'incident : RandomForest si assez d'exemples étiquetés, sinon règles ;
  8. sauvegarde models/model.joblib + models/metadata.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier

from .data import load_csv_dir, load_labels, mask_labeled
from .features import DEFAULT_WINDOW, build_features, service_of
from .model import SCENARIO_TO_TYPE, Baseline, DetectionModel, RobustZModel, constant_features, fit_robust_scaler, scale_clipped
from .threshold import choose_threshold, detection_delay

MIN_EXAMPLES_PER_TYPE = 3


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Nettoyage expliqué : doublons de temps, trous, colonnes constantes (gardées : utiles en cas de panne)."""
    report = {"rows_before": int(len(raw))}
    raw = raw[~raw.index.duplicated(keep="last")].sort_index()
    steps = raw.index.to_series().diff().dt.total_seconds().dropna()
    step = float(steps.mode().iloc[0]) if not steps.empty else 5.0
    gaps = int((steps > 2 * step).sum())
    constant = [c for c in raw.columns if raw[c].nunique(dropna=True) <= 1]
    missing_ratio = float(raw.isna().mean().mean())
    raw = raw.ffill().fillna(0.0)
    report.update({"rows_after": int(len(raw)), "step_seconds": step, "gaps_detected": gaps,
                   "constant_columns": len(constant), "missing_ratio_before_fill": round(missing_ratio, 4)})
    return raw, report


def fit_isolation_forest(x: np.ndarray, n_estimators: int, contamination: float, seed: int) -> IsolationForest:
    forest = IsolationForest(n_estimators=n_estimators, contamination=contamination, max_samples="auto", random_state=seed, n_jobs=-1)
    forest.fit(x)
    return forest


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Entraîne le détecteur d'anomalies (Isolation Forest).")
    parser.add_argument("--data-dir", default="ml/data")
    parser.add_argument("--labels", default="ml/data/labels.csv")
    parser.add_argument("--out", default="ml/detection/models")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--holdout", type=float, default=0.25, help="part du normal réservée au choix du seuil")
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--contamination", type=float, default=0.01)
    parser.add_argument("--target-false-alerts-per-hour", type=float, default=1.0)
    parser.add_argument("--confirm-n", type=int, default=2)
    parser.add_argument("--confirm-m", type=int, default=3)
    parser.add_argument("--recover-r", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    machine = {"confirm_n": args.confirm_n, "confirm_m": args.confirm_m, "recover_r": args.recover_r}

    # 1-2. données, nettoyage, périodes à exclure
    raw, clean_report = clean(load_csv_dir(args.data_dir))
    labels = load_labels(args.labels)
    labeled = mask_labeled(raw.index, labels)
    features_all = build_features(raw, window=args.window)
    normal = features_all[~labeled.to_numpy()]
    print(f"données : {len(raw)} points, {len(raw.columns)} colonnes, pas {clean_report['step_seconds']}s ; normal : {len(normal)} points, étiquetés exclus : {int(labeled.sum())}")
    if len(normal) < 100:
        print("KO : pas assez de données normales (minimum 100 points). Laissez tourner le trafic plus longtemps.")
        return 1

    # 3. découpe chronologique
    split = int(len(normal) * (1 - args.holdout))
    train_x, holdout_x = normal.iloc[:split], normal.iloc[split:]
    feature_names = list(features_all.columns)

    # 4-5. normalisation (entraînement seulement) + Isolation Forest
    scaler = fit_robust_scaler(train_x.to_numpy(dtype=float))
    forest = fit_isolation_forest(scale_clipped(scaler, train_x.to_numpy(dtype=float)), args.n_estimators, args.contamination, args.seed)
    baseline = Baseline(median=train_x.median(), mad=(train_x - train_x.median()).abs().median())
    per_service = {}
    for service in ("poupal-auth", "poupal-api", "poupal-gateway", "poupal-db"):
        columns = [c for c in feature_names if service_of(c) == service]
        if len(columns) >= 3:
            s_scaler = fit_robust_scaler(train_x[columns].to_numpy(dtype=float))
            per_service[service] = (columns, s_scaler, fit_isolation_forest(scale_clipped(s_scaler, train_x[columns].to_numpy(dtype=float)), 100, args.contamination, args.seed))
    version = datetime.now(timezone.utc).strftime("%Y.%m.%d-%H%M")
    model = DetectionModel(version=version, feature_names=feature_names, window=args.window, scaler=scaler, forest=forest, baseline=baseline, per_service=per_service,
                           constant_mask=constant_features(train_x.to_numpy(dtype=float), feature_names))
    return finish(args, model, features_all, train_x, holdout_x, labels, labeled, clean_report, machine)


def finish(args, model: DetectionModel, features_all: pd.DataFrame, train_x: pd.DataFrame, holdout_x: pd.DataFrame,
           labels: pd.DataFrame, labeled: pd.Series, clean_report: dict, machine: dict) -> int:
    """Seuil, référence simple, type d'incident, évaluation rapide et sauvegarde."""
    step = clean_report["step_seconds"]

    # 6. seuil sur la réserve normale (jamais vue à l'entraînement)
    holdout_scores = model.score(holdout_x)
    threshold, curve = choose_threshold(holdout_scores, step, args.target_false_alerts_per_hour, **machine)
    model.threshold = threshold
    reference = RobustZModel(model.baseline)
    ref_scores = reference.score(holdout_x)
    ref_threshold, ref_curve = choose_threshold(ref_scores, step, args.target_false_alerts_per_hour, **machine)
    print(f"seuil Isolation Forest : {threshold:.4f} ; seuil référence z robuste : {ref_threshold:.2f}")

    # 7. type d'incident : RandomForest si assez d'exemples étiquetés par type, sinon règles
    scenario_rows = []
    for _, row in labels.iterrows():
        kind = SCENARIO_TO_TYPE.get(str(row["type"]))
        if kind:
            inside = features_all[(features_all.index >= row["start"]) & (features_all.index <= row["end"])]
            scores = model.score(inside) if len(inside) else np.array([])
            inside = inside[scores > threshold]
            if len(inside):
                scenario_rows.append((kind, inside))
    counts: dict[str, int] = {}
    for kind, rows in scenario_rows:
        counts[kind] = counts.get(kind, 0) + 1
    type_method = "regles"
    if len(counts) >= 2 and all(v >= MIN_EXAMPLES_PER_TYPE for v in counts.values()):
        x = pd.concat([rows for _, rows in scenario_rows])
        y = np.concatenate([[kind] * len(rows) for kind, rows in scenario_rows])
        clf = RandomForestClassifier(n_estimators=100, random_state=args.seed, class_weight="balanced").fit(x.to_numpy(dtype=float), y)
        model.type_classifier, model.type_classifier_features = clf, list(x.columns)
        type_method = "random_forest"
    print(f"type d'incident : {type_method} (scénarios étiquetés par type : {counts or 'aucun'})")

    # évaluation rapide des scénarios étiquetés (détail complet dans evaluate.py)
    all_scores = pd.Series(model.score(features_all), index=features_all.index)
    ref_all = pd.Series(reference.score(features_all), index=features_all.index)
    scenarios = []
    for _, row in labels.iterrows():
        if str(row["type"]) not in SCENARIO_TO_TYPE and str(row["type"]) != "attack":
            continue
        result = detection_delay(all_scores, threshold, row["start"], row["end"], **machine)
        ref_result = detection_delay(ref_all, ref_threshold, row["start"], row["end"], **machine)
        scenarios.append({"type": str(row["type"]), "start": row["start"].isoformat(), "end": row["end"].isoformat(),
                          "isolation_forest": result, "robust_z": ref_result})
    detected = sum(1 for s in scenarios if s["isolation_forest"]["detected"])

    # 8. sauvegarde
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "model.joblib")
    metadata = {
        "version": model.version,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_period": {"start": train_x.index.min().isoformat(), "end": train_x.index.max().isoformat(), "points": int(len(train_x))},
        "holdout_period": {"start": holdout_x.index.min().isoformat(), "end": holdout_x.index.max().isoformat(), "points": int(len(holdout_x))},
        "step_seconds": step,
        "data_cleaning": clean_report,
        "labeled_points_excluded": int(labeled.sum()),
        "features": model.feature_names,
        "feature_count": len(model.feature_names),
        "window": model.window,
        "hyperparameters": {"n_estimators": args.n_estimators, "contamination": args.contamination, "scaler": "RobustScaler", "seed": args.seed},
        "state_machine": machine,
        "threshold": threshold,
        "threshold_curve": curve,
        "reference_robust_z": {"threshold": ref_threshold, "threshold_curve": ref_curve},
        "incident_type_method": type_method,
        "per_service_models": sorted(model.per_service),
        "constant_features": [n for n, c in zip(model.feature_names, model.constant_mask) if c],
        "evaluation": {"scenarios": scenarios, "scenarios_detected": f"{detected}/{len(scenarios)}",
                       "false_alerts_per_hour_holdout": next((c["false_alerts_per_hour"] for c in curve if c["threshold"] == round(threshold, 6)), None)},
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"modèle {model.version} : {len(model.feature_names)} variables, scénarios détectés {detected}/{len(scenarios)} -> {out / 'model.joblib'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
