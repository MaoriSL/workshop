# Infrastructure Poupal — compose, supervision, automatisation

Plateforme de paiement **fictive** (démonstrateur Resilience-Alpha) : tout est simulé, aucun paiement
réel. Le fichier `docker-compose.yml` démarre la plateforme, sa supervision, le générateur de
trafic et le détecteur d'anomalies. La console d'attaque est optionnelle et isolée dans le profil
Compose `attack` ; `ansible/` contient les playbooks de remédiation.

## Démarrage (PowerShell ou WSL2, depuis la racine du dépôt)

```powershell
Copy-Item infra\.env.example infra\.env      # puis remplacer chaque valeur change-me-*
bash scripts/gen_keys.sh                     # clés JWT dans secrets/ (Git Bash ou WSL2)
cd infra; docker compose up -d --build       # plateforme sans console d'attaque
docker compose ps                            # tout doit passer "healthy"
```

Sous WSL2 : `cp infra/.env.example infra/.env && scripts/gen_keys.sh && (cd infra && docker compose up -d --build)`.
Si le port 8080 est déjà pris sur le PC, changer `GATEWAY_PORT` dans `infra/.env`.
Arrêt : `docker compose down` (`-v` pour repartir d'une base vide : l'init SQL est rejouée).

La console d'attaque n'est pas démarrée par cette commande. Pour l'activer sur le PC attaquant :

```bash
cd infra
docker compose --profile attack up -d --build attack-orchestrator attack-console
```

Pour l'arrêter sans toucher au reste de la plateforme :

```bash
docker compose --profile attack stop attack-console attack-orchestrator
```

## Réseaux et ports

| Réseau | Conteneurs | Rôle |
|---|---|---|
| `edge` | gateway, front, supervision, traffic-gen, nginx-exporter, ansible-runner | exposition : seule la gateway publie un port |
| `backend` | db, auth, api, gateway, postgres-exporter, remediation-engine, ansible-runner | cœur métier ; **la base n'est que sur backend** |
| `monitoring` | prometheus, grafana, loki, alloy, exporters, proxys Docker, anomaly-detector, remediation-engine, ansible-runner, auth, api | supervision (auth/api y sont scrapés) |
| `console` | attack-console, attack-orchestrator | réseau dédié de la console d'attaque optionnelle |

| Port publié | Adresse | Service |
|---|---|---|
| `GATEWAY_PORT` (8080) | `0.0.0.0` | gateway nginx : front `/`, `/auth/`, `/api/` — seul accès depuis le réseau du groupe |
| `GRAFANA_PORT` (3000) | `127.0.0.1` | Grafana (admin / `GRAFANA_ADMIN_PASSWORD`, accès anonyme désactivé) |
| `PROMETHEUS_PORT` (9090) | `127.0.0.1` | Prometheus (PC Hôte uniquement) |

Rien d'autre n'est publié : Loki, exporters, base de données, services auth/api et détecteur
restent sur les réseaux Docker. `/internal/*` de l'API est bloqué (403) par la gateway.

## Supervision

- **Prometheus** (`prometheus/`) : scrape toutes les 5 s de auth, api, gateway (stub_status via
  nginx-prometheus-exporter), base (postgres_exporter, rôle SQL `poupal_exporter` en lecture seule,
  `pg_monitor`), conteneurs et détecteur. Rétention 7 jours / 1 Go. `rules/recording.yml` : 21 règles
  `poupal:*` = les variables du modèle ML (requêtes/s, 4xx/5xx, p50/p95, échecs de connexion/min,
  transactions/min par statut, CPU/mémoire/réseau/redémarrages par conteneur, connexions base).
  `rules/alerts.yml` : filet de sécurité uniquement (service down, 5xx, p95, rafale d'échecs de
  connexion, redémarrages) ; la détection principale est le modèle ML.
- **Conteneurs** : cAdvisor **ne fonctionne pas** sous Docker Desktop / WSL2 avec le magasin d'images
  containerd (driver `overlayfs`) : « failed to identify the read-write layer ID », aucune métrique par
  conteneur. Il est remplacé par `tools/docker-stats-exporter` (Python stdlib, 20 Mo), qui lit l'API
  Docker via le proxy **en lecture seule** et publie les mêmes noms de métriques
  (`container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, réseau, `container_restart_count`,
  label `container` = service compose). Sur un hôte Linux classique, cAdvisor peut être réintroduit
  sans changer les règles ni les dashboards.
- **Loki + Alloy** (`loki/`, `alloy/`) : Alloy découvre les conteneurs du projet via le proxy en lecture
  seule, analyse les lignes JSON et n'envoie que trois labels : `service`, `level`, `event`.
  `request_id`, `user_id`, `client_ip`… restent dans la ligne (`{service="poupal-api"} | json | request_id="…"`).
  Les logs nginx de la gateway sont en JSON (IP, route, statut, temps de réponse, user-agent).
  Rétention 3 jours.
- **Grafana** (`grafana/`) : datasources et 5 dashboards provisionnés par fichiers (dossier « Poupal ») :
  Santé des services, Métier, Conteneurs, Logs, Détection d'anomalies (ML). Gros chiffres et couleurs
  lisibles à distance (Clip Chrono).

## Automatisation — Ansible (`ansible/`)

Ansible ne tourne pas nativement sous Windows : le conteneur `ansible-runner` (profil `tools`, démarré
à la demande) exécute les playbooks. Il n'accède **jamais** au socket Docker : il passe par
`docker-socket-proxy-ansible`, qui n'autorise que lister / inspecter / démarrer / arrêter / redémarrer /
créer / supprimer des conteneurs, exec, images, réseaux, volumes — pas de build, pas de swarm, pas
d'accès système. Un attaquant qui prendrait le contrôle de l'outil de réparation ne pourrait donc
pas faire plus que l'outil lui-même. Détails et choix dans `ansible/README.md`.

```powershell
infra\ansible\run.ps1 verify                          # PowerShell
infra/ansible/run.sh restart_service -e service=api   # WSL2 / Git Bash
```

| Playbook | Rôle |
|---|---|
| `deploy.yml` | démarre toute la plateforme (images déjà construites), attend « healthy », smoke test |
| `restart_service.yml` | redémarre un service et attend « healthy » (= restaurer la disponibilité) |
| `recreate_service.yml` | supprime le conteneur et le recrée depuis l'image d'origine (conteneur compromis) |
| `rollback.yml` | revient à l'image `previous` (posée par deploy.yml) d'un service |
| `backup_db.yml` / `restore_db.yml` | `pg_dump` horodaté dans le volume `db-backups` ; restauration de la dernière sauvegarde valide + `/internal/consistency` |
| `block_ip.yml` / `unblock_ip.yml` | liste de blocage nginx (`deny`), rechargement sans coupure (`nginx -s reload`) |
| `verify.yml` | `scripts/smoke_test.py` + `/internal/consistency` → `VERIFY OK` / `VERIFY KO` |

Redémarrer = restaurer la disponibilité ; recréer + restaurer = traiter une compromission ou une
corruption. Chaque playbook écrit une ligne JSON `event=remediation_action` (action, service, résultat,
durée) sur stdout et dans Loki (`{service="remediation"}`) : la chronologie d'une réparation est retraçable.

## Remédiation automatique et dashboard de supervision

- `remediation-engine` (`services/remediation`) reçoit les incidents signés du détecteur ML, choisit un
  plan dans un catalogue fixe et exécute les playbooks via `ansible-runner`, désormais service
  permanent qui expose une API minimale d'exécution (`infra/ansible/runner_api.py`, liste blanche de
  playbooks, jeton `RUNNER_TOKEN`). La reprise est **prouvée** par `scripts/smoke_test.py` (nouvelle
  transaction) et `/internal/consistency`. Runbook, catalogue et analyse de sécurité : `docs/remediation.md`.
- `supervision` (`frontend/supervision`) : dashboard React servi par la gateway sous
  `/supervision/`. Il reste en lecture seule pour l'état des incidents, avec une action bornée
  supplémentaire pour consulter les IP bannies et demander leur déblocage via le playbook
  `unblock_ip`.
- Répétition : `python ml/detection/scenarios/inject.py outage --service api --mode pause --duration 90`
  et observer sur http://localhost:8080/supervision/ : anomalie détectée → action → transaction de
  preuve → SERVICE RÉTABLI (≈ 35 s au total, ≈ 17 s de la détection à la preuve le 20/10/2026).

## Générateur de trafic normal (`tools/traffic-gen`)

Dix utilisateurs fictifs (comptes du seed) passent par la gateway comme de vrais clients : connexion,
solde, historique, petits virements en circuit fermé (les soldes restent stables, la cohérence reste
vraie), pauses aléatoires, périodes calmes et chargées, erreur de mot de passe occasionnelle.
Variables : `TRAFFIC_ENABLED`, `TRAFFIC_USERS`, `TRAFFIC_INTENSITY`. Mode `TRAFFIC_MODE=bruteforce`
réservé aux scénarios d'évaluation du détecteur.

## Export pour le ML

`python scripts/export_metrics.py --since 2h --step 5s` → `ml/data/metrics-<date>-<since>-<step>.csv`
(une ligne par pas, une colonne par variable et par service, aucune colonne vide).

## Budget mémoire (limite par conteneur dans le compose)

| Groupe | Limites | Mesuré (`docker stats`, trafic normal) |
|---|---|---|
| Supervision (prometheus 512, grafana 256, loki 384, alloy 192, docker-stats-exporter 64, nginx-exporter 32, postgres-exporter 64, 2 proxys 2×32) | 1 568 Mo | ≈ 380 Mo |
| Plateforme (db 384, auth 192, api 192, front 48, gateway 64) | 880 Mo | ≈ 190 Mo |
| Détecteur ML (512) + trafic (96) | 608 Mo | ≈ 165 Mo |

Total mesuré : **≈ 730 Mo** pour le socle observabilité et applicatif mesuré le 20/10/2026
(`docker stats --no-stream`) ; la console d'attaque optionnelle n'est pas incluse dans ce chiffre.
Les images portent toutes un tag de version précis.

## Checklist de vérification (validée le 20/10/2026)

- [x] Toutes les cibles Prometheus sont UP (`/api/v1/targets` : prometheus, auth, api, gateway, db, containers, detector).
- [x] Les dashboards Grafana affichent du trafic en direct (générateur actif, 5 dashboards provisionnés sans erreur).
- [x] Les logs de chaque service sont visibles et filtrables dans Grafana (labels `service`, `level`, `event`).
- [x] Playbooks testés : verify, restart_service (api), recreate_service (api, gateway), rollback (api), backup_db,
      restore_db, block_ip / unblock_ip (+ refus d'une valeur injectée), deploy.
- [x] L'export CSV produit un fichier exploitable (301 lignes / 102 colonnes pour 25 min, aucune colonne vide).
- [x] Consommation mémoire totale dans le budget (voir tableau).
- [x] Détecteur ML : passage en ANOMALIE en < 30 s lors d'une pause de l'api, retour à NORMAL après la fin du scénario.
- [x] Chaîne zero-touch : api en pause, brute force et base ralentie → RÉTABLI avec transaction de preuve (15,6 s / 17,4 s / 3,7 s de la détection à la preuve) ; pic de charge non détecté (limite documentée).
