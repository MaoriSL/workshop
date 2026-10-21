# ml/data — jeux de données pour la détection d'anomalies

Dossier de sortie de `scripts/export_metrics.py` : des extraits CSV des métriques
Prometheus de la plateforme Poupal, prêts à être lus par `ml/detection`.
Les fichiers `*.csv` générés ne sont **pas versionnés** (`.gitignore`) : chacun les
régénère depuis sa propre pile.

> **Données fictives.** Poupal est une plateforme de paiement inventée pour le Workshop
> EPSI Resilience-Alpha (environnement de démonstration). Le trafic vient du générateur
> `tools/traffic-gen`, les comptes sont des comptes de démonstration : aucune donnée
> bancaire ou personnelle réelle n'apparaît dans ces fichiers.

## Générer un export

Pré-requis : la pile tourne (`cd infra && docker compose up -d`) et Prometheus est publié
sur `127.0.0.1:9090` (variable `PROMETHEUS_PORT` dans `infra/.env` ; si elle change,
passer `--prometheus-url http://localhost:<port>`).

    # dernière heure, une ligne toutes les 15 s (valeurs par défaut)
    python scripts/export_metrics.py

    # 10 minutes de trafic pour un essai rapide
    python scripts/export_metrics.py --since 10m --step 15s

    # une journée complète pour l'entraînement (le script découpe la requête en tranches)
    python scripts/export_metrics.py --since 1d --step 30s

| Option             | Défaut                                              | Rôle                                                              |
|--------------------|-----------------------------------------------------|-------------------------------------------------------------------|
| `--prometheus-url` | `POUPAL_PROMETHEUS_URL` ou `http://localhost:9090`  | URL de Prometheus                                                 |
| `--since`          | `1h`                                                | période exportée, terminée maintenant : `30m`, `2h`, `1d`         |
| `--step`           | `15s`                                               | pas de temps entre deux lignes                                    |
| `--out-dir`        | `ml/data`                                           | dossier de sortie                                                 |
| `--rules-prefix`   | `poupal:`                                           | ne garde que les règles d'enregistrement portant ce préfixe       |

Bibliothèque standard uniquement : n'importe quel Python ≥ 3.10 convient, sans installation.
Code de retour 1 si Prometheus est injoignable, qu'aucune règle ne correspond ou qu'aucune
donnée n'a été renvoyée (pile tout juste démarrée : attendre quelques minutes).

## Format du fichier

Nom : `metrics-<date UTC de l'export>-<since>-<step>.csv`, ex. `metrics-20261020T093000Z-10m-15s.csv`.

Une ligne par pas de temps, de `maintenant − since` à `maintenant` (bornes arrondies au pas).
Colonnes :

- `timestamp` : ISO 8601 en UTC, ex. `2026-10-20T09:30:00Z` ;
- une colonne par série de chaque règle d'enregistrement (`infra/prometheus/rules/recording.yml`),
  nommée `<règle sans préfixe, ':' → '_'>__<valeur du label service | container | status | job>` :

| Règle Prometheus                                   | Label     | Colonne                                        |
|----------------------------------------------------|-----------|------------------------------------------------|
| `poupal:http_requests_per_second:rate1m{service}`  | service   | `http_requests_per_second_rate1m__poupal-api`  |
| `poupal:container_memory_bytes{container}`         | container | `container_memory_bytes__db`                   |
| `poupal:transactions_per_minute{status}`           | status    | `transactions_per_minute__completed`           |
| `poupal:service_up{job}`                           | job       | `service_up__api`                              |
| `poupal:db_connections_active` (sans label)        | —         | `db_connections_active`                        |

Les colonnes sont triées par nom. Les valeurs sont celles renvoyées par Prometheus (texte
numérique, ex. `0.4`, `1.2e+08`) dans l'unité de la règle : secondes, octets, cœurs,
requêtes/s, événements par minute, 0/1 pour `service_up`.

Valeurs manquantes (service pas encore démarré, trou de collecte, `NaN` d'un quantile sans
trafic) : la dernière valeur connue est reportée, sinon `0`. Une colonne sans aucune valeur sur
la période est supprimée : il n'y a jamais de colonne vide.

Extrait :

    timestamp,container_cpu_cores_rate1m__api,container_cpu_cores_rate1m__auth,...,service_up__api,...
    2026-10-20T09:20:00Z,0.0123,0.0071,...,1,...
    2026-10-20T09:20:15Z,0.0119,0.0068,...,1,...

## Lecture côté ML

    import pandas as pd

    df = pd.read_csv("ml/data/metrics-20261020T093000Z-1h-15s.csv", index_col="timestamp", parse_dates=True)
    X = df.to_numpy()   # une observation par ligne, une variable par colonne

Le jeu de colonnes peut varier d'un export à l'autre (conteneur absent, règle ajoutée) :
aligner les colonnes sur celles du jeu d'entraînement avant de prédire.
