#!/usr/bin/env python3
"""
Exporte les métriques Prometheus de Poupal en CSV, pour l'apprentissage du modèle
de détection d'anomalies (ml/detection).

    python scripts/export_metrics.py                      # dernière heure, pas de 15 s
    python scripts/export_metrics.py --since 2h --step 30s

Principe : les règles d'enregistrement de Prometheus (infra/prometheus/rules/recording.yml,
toutes préfixées « poupal: ») SONT les variables du modèle. Le script :
    1. liste ces règles via l'API Prometheus          (GET /api/v1/rules?type=record) ;
    2. interroge chacune sur la période demandée      (GET /api/v1/query_range) ;
    3. aligne toutes les séries sur une même grille de temps : une ligne par pas de temps,
       une colonne par série, et écrit le tout en CSV.

Colonnes : « timestamp » (ISO 8601, UTC) puis, triées par nom,
    <règle sans préfixe, ':' remplacé par '_'>__<valeur du label service | container | status | job>
    ex. http_requests_per_second_rate1m__poupal-api, container_memory_bytes__db, service_up__api.
    Une règle sans aucun de ces labels (ex. poupal:db_connections_active) donne une colonne
    sans suffixe : db_connections_active.
Valeurs manquantes (série pas encore apparue, trou de collecte, NaN d'un quantile sans trafic) :
    dernière valeur connue, sinon 0. Les colonnes entièrement vides sont supprimées.

Sortie : ml/data/metrics-<UTC %Y%m%dT%H%M%SZ>-<since>-<step>.csv (fichiers ignorés par Git).
Code de retour : 0 si le CSV est écrit ; 1 si Prometheus est injoignable, si aucune règle ne
correspond au préfixe ou si aucune donnée n'a été renvoyée.
Bibliothèque standard uniquement. Données FICTIVES : environnement de démonstration.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Label qui identifie une série dans le nom de sa colonne, par ordre de priorité.
COLUMN_LABELS = ("service", "container", "status", "job")

# Prometheus refuse les requêtes de plus de 11 000 points par série :
# une longue période est découpée en tranches de cette taille.
MAX_POINTS_PER_QUERY = 10_000

# Durées acceptées : 30s, 10m, 2h, 1d
DURATION_RE = re.compile(r"^(\d+)([smhd])$")
DURATION_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class ExportError(Exception):
    """Erreur bloquante, avec un message lisible pour l'utilisateur."""


# --------------------------------------------------------------------------- utilitaires

def parse_duration(text: str) -> int:
    """'15s', '10m', '2h', '1d' -> nombre de secondes (entier strictement positif)."""
    match = DURATION_RE.match(text.strip())
    if not match or int(match.group(1)) == 0:
        raise ValueError(f"durée invalide : {text!r} (attendu : 30s, 10m, 2h, 1d)")
    return int(match.group(1)) * DURATION_SECONDS[match.group(2)]


def iso_utc(epoch_seconds: int) -> str:
    """Horodatage ISO 8601 en UTC, ex. 2026-10-20T09:30:00Z."""
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_finite(value: str) -> bool:
    """Prometheus renvoie 'NaN' ou '+Inf' (quantile sans trafic, division) : on les traite comme absents."""
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False


def column_name(rule: str, prefix: str, labels: dict[str, str]) -> str:
    """Nom de colonne d'une série : règle sans préfixe (':' -> '_') + '__' + label identifiant."""
    base = rule[len(prefix):] if rule.startswith(prefix) else rule
    base = base.replace(":", "_")
    for label in COLUMN_LABELS:
        if label in labels:
            return f"{base}__{labels[label]}"
    return base


# --------------------------------------------------------------------------- API Prometheus

def prometheus_get(base_url: str, path: str, params: dict[str, str], timeout: float) -> dict:
    """Appel GET à l'API Prometheus ; renvoie le champ « data » ou lève ExportError."""
    url = f"{base_url}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()[:300]
        raise ExportError(f"HTTP {error.code} sur {path} : {detail or 'sans détail'}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ExportError(f"Prometheus injoignable sur {base_url} ({error})") from error
    except json.JSONDecodeError as error:
        raise ExportError(f"réponse non JSON sur {path} (est-ce bien Prometheus ?)") from error
    if payload.get("status") != "success":
        raise ExportError(f"{path} : {payload.get('errorType', 'erreur')} — {payload.get('error', '?')}")
    return payload.get("data", {})


def prometheus_now(base_url: str, timeout: float) -> int:
    """
    Heure courante de Prometheus (horloge du conteneur), référence du « maintenant » de l'export.
    Sous Docker Desktop, l'horloge de la VM peut dériver de celle du PC après une mise en veille :
    se caler sur Prometheus évite un export vide ou décalé.
    """
    data = prometheus_get(base_url, "/api/v1/query", {"query": "time()"}, timeout)
    return int(float(data["result"][1]))  # résultat scalaire : [horodatage, "valeur"]


def list_recording_rules(base_url: str, prefix: str, timeout: float) -> list[str]:
    """Noms des règles d'enregistrement commençant par le préfixe (triés, sans doublon)."""
    data = prometheus_get(base_url, "/api/v1/rules", {"type": "record"}, timeout)
    names: set[str] = set()
    for group in data.get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("type") == "recording" and rule.get("name", "").startswith(prefix):
                names.add(rule["name"])
    return sorted(names)


def query_series(base_url: str, rule: str, grid: list[int], step: int, timeout: float) -> list[tuple[dict[str, str], dict[int, str]]]:
    """
    Toutes les séries d'une règle sur la grille : [(labels, {horodatage: valeur})].
    Seules les valeurs finies sont conservées (NaN / Inf = absentes).
    """
    series: dict[tuple, dict[int, str]] = {}  # labels (figés en tuple) -> points
    for offset in range(0, len(grid), MAX_POINTS_PER_QUERY):
        chunk = grid[offset:offset + MAX_POINTS_PER_QUERY]
        params = {"query": rule, "start": str(chunk[0]), "end": str(chunk[-1]), "step": str(step)}
        data = prometheus_get(base_url, "/api/v1/query_range", params, timeout)
        for item in data.get("result", []):
            labels = {key: value for key, value in item.get("metric", {}).items() if key != "__name__"}
            points = series.setdefault(tuple(sorted(labels.items())), {})
            for timestamp, value in item.get("values", []):
                if is_finite(value):
                    points[int(float(timestamp))] = value
    return [(dict(key), points) for key, points in series.items()]


# --------------------------------------------------------------------------- construction du tableau

def collect_columns(base_url: str, rules: list[str], prefix: str, grid: list[int], step: int, timeout: float) -> dict[str, dict[int, str]]:
    """Interroge chaque règle et range ses séries par nom de colonne (unique)."""
    columns: dict[str, dict[int, str]] = {}
    for rule in rules:
        found = query_series(base_url, rule, grid, step, timeout)
        print(f"    {rule:<48} {len(found):>2} série(s)")
        for labels, points in found:
            name = column_name(rule, prefix, labels)
            if name in columns:
                # Deux séries d'une même règle avec le même label identifiant (ex. deux instances) :
                # on numérote plutôt que d'écraser, et on le signale.
                suffix = 2
                while f"{name}__{suffix}" in columns:
                    suffix += 1
                print(f"      ! colonne {name} déjà prise, série renommée {name}__{suffix} (labels : {labels})")
                name = f"{name}__{suffix}"
            columns[name] = points
    return columns


def build_table(grid: list[int], columns: dict[str, dict[int, str]]) -> tuple[list[str], list[list[str]], int]:
    """
    Aligne les colonnes sur la grille : valeur manquante = dernière valeur connue, sinon 0.
    Renvoie (en-tête, lignes, nombre de colonnes vides supprimées).
    """
    names = sorted(name for name, points in columns.items() if points)
    dropped = len(columns) - len(names)
    last_known = {name: "0" for name in names}
    rows: list[list[str]] = []
    for timestamp in grid:
        row = [iso_utc(timestamp)]
        for name in names:
            value = columns[name].get(timestamp)
            if value is not None:
                last_known[name] = value
            row.append(last_known[name])
        rows.append(row)
    return ["timestamp", *names], rows, dropped


# --------------------------------------------------------------------------- programme principal

def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # consoles Windows en cp1252
    default_out = Path(__file__).resolve().parent.parent / "ml" / "data"

    parser = argparse.ArgumentParser(description="Exporte les règles d'enregistrement Prometheus de Poupal en CSV (jeu de données ML).")
    parser.add_argument("--prometheus-url", default=os.environ.get("POUPAL_PROMETHEUS_URL", "http://localhost:9090"),
                        help="URL de Prometheus (défaut : POUPAL_PROMETHEUS_URL ou http://localhost:9090)")
    parser.add_argument("--since", default="1h", help="période à exporter, terminée maintenant : 30m, 2h, 1d (défaut : 1h)")
    parser.add_argument("--step", default="15s", help="pas de temps entre deux lignes (défaut : 15s)")
    parser.add_argument("--out-dir", type=Path, default=default_out, help="dossier de sortie (défaut : ml/data)")
    parser.add_argument("--rules-prefix", default="poupal:", help="préfixe des règles à exporter (défaut : poupal:)")
    parser.add_argument("--timeout", type=float, default=30.0, help="délai par requête HTTP, en secondes")
    args = parser.parse_args(argv)

    try:
        since_seconds, step_seconds = parse_duration(args.since), parse_duration(args.step)
    except ValueError as error:
        parser.error(str(error))
    if since_seconds < step_seconds:
        parser.error("--since doit être supérieur ou égal à --step")

    base_url = args.prometheus_url.rstrip("/")
    print(f"Export des métriques Poupal — {base_url}")
    try:
        # Grille de temps : fin = « maintenant » selon Prometheus, arrondi au pas ; début = fin - since.
        now = prometheus_now(base_url, args.timeout)
        drift = int(time.time()) - now
        if abs(drift) > 60:
            print(f"    ! horloge de Prometheus décalée de {drift:+d} s par rapport au PC : l'export suit l'heure de Prometheus")
        end = now // step_seconds * step_seconds
        start = end - (since_seconds // step_seconds) * step_seconds
        grid = list(range(start, end + 1, step_seconds))
        print(f"    période {iso_utc(start)} → {iso_utc(end)} (pas {args.step})")

        rules = list_recording_rules(base_url, args.rules_prefix, args.timeout)
        if not rules:
            print(f"KO  aucune règle d'enregistrement avec le préfixe {args.rules_prefix!r} (rules/recording.yml chargé ?)")
            return 1
        print(f"    {len(rules)} règle(s) d'enregistrement trouvée(s)")
        columns = collect_columns(base_url, rules, args.rules_prefix, grid, step_seconds, args.timeout)
    except ExportError as error:
        print(f"KO  {error}")
        return 1

    header, rows, dropped = build_table(grid, columns)
    if len(header) == 1:
        print("KO  aucune donnée sur la période : Prometheus vient-il de démarrer ? (réessayer dans quelques minutes)")
        return 1

    exported_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path: Path = args.out_dir / f"metrics-{exported_at}-{args.since}-{args.step}.csv"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)

    print("OK  export terminé")
    print(f"    lignes   : {len(rows)} (une toutes les {args.step})")
    print(f"    colonnes : {len(header) - 1} + timestamp ({dropped} colonne(s) vide(s) retirée(s))")
    print(f"    période  : {iso_utc(start)} → {iso_utc(end)} (UTC, {args.since})")
    print(f"    fichier  : {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
