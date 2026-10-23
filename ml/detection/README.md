# Détection d'anomalies par ML — `ml/detection`

Le modèle apprend le fonctionnement **normal** de Poupal (métriques Prometheus) et signale ce qui
s'en écarte. Aucun seuil métier codé en dur : le seul seuil est celui du score d'anomalie, choisi
automatiquement sur une période normale jamais vue à l'entraînement. Le détecteur **détecte mais
n'agit pas** : il envoie un incident signé au moteur de remédiation (`docs/api/incident.md`).

## Fichiers

| Fichier | Rôle |
|---|---|
| `features.py` | calcul des variables : UN seul module, identique à l'entraînement et en temps réel |
| `data.py` | chargement des CSV (`ml/data/`), de `labels.csv`, lecture en direct dans Prometheus (mêmes colonnes) |
| `model.py` | Isolation Forest + référence « z robuste », explication (service suspecté, 3 variables, type d'incident) |
| `threshold.py` | choix du seuil (< 1 fausse alerte / h) en rejouant la machine à états ; délais de détection |
| `train.py` | entraînement → `models/model.joblib` + `models/metadata.json` |
| `evaluate.py` | évaluation sur les périodes étiquetées → `reports/` (JSON, Markdown, PNG) |
| `scenarios/inject.py` | pannes contrôlées étiquetées (pause/stop d'un service, surcharge, brute force, base lente) |
| `service/` | détecteur temps réel (FastAPI, conteneur `anomaly-detector`) : machine à états, webhook HMAC |
| `tests/` | pytest : identité des variables, machine à états, signature HMAC, démarrage sans Prometheus |
| `REPORT.md` | rapport pour le dossier d'ingénierie |

## Cycle complet (depuis la racine du dépôt, venv Python 3.12 avec `requirements.txt`)

```bash
# 1. exporter l'historique des métriques (la plateforme et le générateur de trafic tournent)
python scripts/export_metrics.py --since 2h --step 5s

# 2. créer des anomalies étiquetées (uniquement sur notre plateforme locale)
python ml/detection/scenarios/inject.py outage --service api --mode pause --duration 90
python ml/detection/scenarios/inject.py db_slow --duration 75
python ml/detection/scenarios/inject.py bruteforce --duration 90
python ml/detection/scenarios/inject.py overload --duration 120 --replicas 3

# 3. réentraîner (exclut automatiquement les périodes de ml/data/labels.csv) puis évaluer
python -m ml.detection.train
python -m ml.detection.evaluate

# 4. recharger le modèle dans le détecteur temps réel
cd infra && docker compose restart anomaly-detector

# 5. tests
python -m pytest -q ml/detection/tests
```

Une attaque réelle (PC Attaquant) s'ajoute à `labels.csv` avec
`python ml/detection/scenarios/inject.py label --type attack --start <ISO> --end <ISO>`, puis `evaluate`.

Les signaux de corrélation SIEM (`waf_block_burst`, `enumeration`, `rate_limited_burst` et
`bruteforce_login`) sont aussi exportés par Prometheus comme variables du modèle. Ils permettent
au détecteur ML de confirmer une attaque bloquée au WAF ou une énumération, même si la requête
n'atteint pas l'API. Après cette modification, le modèle doit être réentraîné avec des données
normales puis des scénarios étiquetés :

```bash
python scripts/export_metrics.py --since 2h --step 5s
python -m ml.detection.train
python -m ml.detection.evaluate
cd infra && docker compose restart anomaly-detector
```

## Service temps réel

Toutes les 5 s : Prometheus → `features.py` → score → machine à états
`NORMAL → SUSPECT → ANOMALIE → RÉTABLISSEMENT → NORMAL` (N dépassements sur M fenêtres pour
confirmer, R fenêtres calmes pour rétablir ; variables `DETECTOR_CONFIRM_N/M`, `DETECTOR_RECOVER_R`).

| Endpoint | Rôle |
|---|---|
| `GET /status` | état, score, seuil, service suspecté, type, 3 variables principales, depuis quand |
| `GET /incidents` | historique des incidents |
| `GET /health`, `GET /ready` | vivacité ; readiness = modèle chargé **et** Prometheus joignable |
| `GET /metrics` | `poupal_anomaly_score`, `poupal_anomaly_threshold`, `poupal_anomaly_state`, `poupal_anomaly_service_score{service}` |

Incidents : `POST REMEDIATION_URL` signé HMAC-SHA256 (`X-Poupal-Signature`), 3 tentatives ; sans URL
configurée, journalisés seulement (`event=anomaly_detected` / `anomaly_resolved` dans Loki).
Le conteneur n'a accès qu'au réseau `monitoring` (lecture de Prometheus), limite mémoire 512 Mo.
