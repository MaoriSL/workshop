# Remédiation automatique Poupal — runbook et justifications

Le moteur (`services/remediation`, conteneur `remediation-engine`) répare la plateforme **sans
intervention humaine**. Principe directeur du sujet : un conteneur qui redémarre n'est pas une
preuve ; la seule preuve acceptée est une **nouvelle transaction fictive qui réussit** après
l'incident, avec des données cohérentes. Toute la conception tourne autour de cela : agir, puis prouver.

## 1. Chaîne complète et budget de temps (Clip Chrono : 60 s)

| Étape | Qui | Budget | Mesuré (répétition du 20/10/2026, api en pause) |
|---|---|---|---|
| Détection | détecteur ML (`anomaly-detector`) : score > seuil sur 2 fenêtres sur 3 | ≤ 30 s | ≈ 18 s |
| Décision + action | moteur : plan du catalogue → playbook Ansible via `ansible-runner` | ≤ 20 s | ≈ 10 s (restart_service) |
| Vérification | healthy → `smoke_test.py` (transaction de preuve) → `/internal/consistency` | ≤ 10 s | ≈ 6 s |
| **Total incident → service prouvé rétabli** | | **< 45 s** | **≈ 35 s** (16,4 s de la détection à la preuve) |

Le dashboard affiche la chronologie horodatée (T+n s) et la durée détection → preuve (`recovery_seconds`).

## 2. Réception des incidents (`receiver.py`)

- `POST /incidents` : corps JSON canonique signé **HMAC-SHA256** (`X-Poupal-Signature`, secret partagé
  `REMEDIATION_HMAC_SECRET`). Signature absente, invalide ou corps altéré → `401`, rien n'est fait.
- Validation stricte (Pydantic) : `suspected_service` dans la **liste blanche** `front, auth, api, db, gateway`
  (ou `inconnu`), `incident_type` dans le catalogue fermé, `incident_id` alphanumérique. Hors contrat → `422`.
- Idempotence : un `incident_id` déjà connu ne déclenche rien (`already_known`). Un seul incident ouvert
  par service (verrou par service) : jamais deux playbooks en parallèle sur le même conteneur.
- `state = NORMAL` du détecteur : simplement noté dans la chronologie (`detector_normal`).

## 3. Catalogue des plans d'action (`policy.py`)

Le moteur reçoit un **type**, jamais une commande. Deux familles de réponse :

- **Restaurer la disponibilité** — le service est tombé ou sature : redémarrer, bloquer la source, recréer.
- **Traiter une compromission ou une corruption** — le conteneur ou les données ne sont plus dignes de
  confiance : recréer depuis l'image d'origine, restaurer la base. Un simple redémarrage serait une fausse
  réponse (le code altéré redémarrerait avec).

| Type | Famille | Niveau 1 | Niveau 2 | Niveau 3 | Pourquoi |
|---|---|---|---|---|---|
| `indisponibilite` | disponibilité | `restart_service` | `recreate_service` | `rollback` (image `previous`) | du moins au plus intrusif : relancer, repartir d'une image saine, revenir à la version précédente |
| `surcharge` | disponibilité | `block_ip` (IP la plus agressive, logs gateway via Loki) | `restart_service` | `recreate_service` | couper la source avant de toucher au service |
| `bruteforce` | disponibilité | `block_ip` | `restart_service` (auth) | — | l'attaquant est identifiable par ses échecs de connexion |
| `db_lente` | disponibilité | `terminate_long_queries` | `restart_service` (db) | `restore_db` | lever les verrous sans redémarrer, puis redémarrer, puis restaurer |
| `compromission` | intégrité | `block_ip` + `recreate_service` | `restore_db` + cohérence | — | image d'origine, pas un redémarrage ; données possiblement altérées |
| `incoherence` | intégrité | `restore_db` | `rollback` (api) | — | soldes faux : dernière sauvegarde valide, puis l'API suspecte |
| `inconnu` | disponibilité | `restart_service` | `recreate_service` | — | réponse générique prudente |

On ne passe au niveau suivant **que si la vérification échoue** (escalade). `block_ip` saute l'étape
(sans compter comme action) quand aucune IP externe agressive n'apparaît : nos propres conteneurs ne
sont jamais bloqués.

## 4. Exécution (`executor.py` → `infra/ansible/runner_api.py`)

- Seuls les playbooks de la liste blanche sont appelables, par leur nom : `restart_service`,
  `recreate_service`, `rollback`, `block_ip`, `unblock_ip`, `terminate_long_queries`, `backup_db`,
  `restore_db`. `deploy` n'y est pas. Jamais de commande shell construite à partir d'une donnée reçue :
  le runner lance `ansible-playbook <fichier> -e clé=valeur` avec une liste d'arguments.
- Paramètres validés deux fois (moteur et runner) : service dans la liste blanche ; IP syntaxiquement
  valide **et hors de notre infrastructure** (boucle locale, réseaux Docker 172.16/12, lien local, plages
  `REMEDIATION_PROTECTED_NETWORKS`, ex. le LAN du PC Hôte). Un attaquant qui usurperait une IP interne ne
  peut pas faire bloquer un composant légitime.
- Délai par action : 30 s (`REMEDIATION_ACTION_TIMEOUT_S`) ; une action qui ne rend pas la main est
  abandonnée et l'escalade continue. Chaque action produit un log JSON `event=remediation_action`
  (action, service, paramètres, résultat, durée) côté moteur **et** côté playbook (Loki).

## 5. Vérification — la preuve (`verifier.py`)

Après chaque action, dans cet ordre, et les trois doivent réussir :
1. le conteneur répond à sa sonde (`/ready` de auth/api, `/gateway/health`, `pg_up` pour la base) ;
2. `scripts/smoke_test.py --json` : connexion d'un compte de démo, envoi de **1,00 €** à un autre compte,
   transaction `completed`, solde débité d'exactement 1,00 € ;
3. `GET /internal/consistency` : aucun solde négatif, somme des soldes conservée.

La transaction de preuve (id, référence, montant, horodatage, statut, soldes avant/après) est conservée
dans l'incident et affichée en grand sur le dashboard.

## 6. Garde-fous (`state.py`)

- **3 actions maximum** par incident, puis état `ECHEC` avec un message clair ; on ne boucle pas.
- **Délai minimum de 5 s** entre deux actions (stabilisation).
- **Disjoncteur** : plus de 8 actions en 10 minutes → état `SURETE`, le moteur cesse d'agir et le signale.
  Réglage : une démo complète enchaîne au plus 4 scénarios × 1 à 2 actions en ~10 min (≈ 6 actions),
  donc le disjoncteur ne se déclenche pas en répétition ; une boucle de pannes (8 actions sans reprise)
  le déclenche. Variables `REMEDIATION_BREAKER_LIMIT` / `REMEDIATION_BREAKER_WINDOW_MIN`.
- **Dry-run** (`REMEDIATION_DRY_RUN=true`) : décide et journalise sans exécuter.
- Cycle de vie horodaté : `RECU → DECIDE → ACTION_EN_COURS → VERIFICATION → RETABLI`
  (ou `ESCALADE` → … → `ECHEC`).

## 7. Sécurité du moteur — et si un attaquant en prenait le contrôle ?

Le moteur a des droits élevés : c'est le composant le plus sensible. Ce qu'il **ne peut pas** faire :

| Menace | Ce qui l'en empêche |
|---|---|
| Déclencher une réparation depuis l'extérieur | la gateway ne proxifie que `GET /api/state`, `/api/incidents`, `/api/events` ; `POST /incidents` n'est joignable que sur le réseau interne et exige la signature HMAC |
| Faire exécuter une commande arbitraire | aucun endpoint d'administration ; le moteur ne connaît que des types d'incident et un catalogue fixe ; le runner n'accepte que des noms de playbooks de sa liste blanche et des variables validées |
| Accéder à Docker | le moteur n'a **aucun** accès au socket ; seul `ansible-runner` y accède, via `docker-socket-proxy-ansible`, limité à lister / inspecter / démarrer / arrêter / redémarrer / créer / supprimer / exec / images / réseaux / volumes (pas de build, pas de swarm, pas d'accès système) |
| Bloquer un composant légitime en usurpant une IP | IP internes refusées, plages protégées configurables |
| Faire boucler les réparations (déni de service par remédiation) | 3 actions par incident, délai minimal, disjoncteur |
| Lire des secrets | le moteur ne reçoit que le secret HMAC, le jeton du runner et le mot de passe de démo du smoke test ; aucun secret de base ni clé JWT |

Il tourne non-root, avec une limite mémoire (256 Mo) et une image à tag de version précis, sur les
réseaux `backend` (sondes, smoke test via la gateway) et `monitoring` (détecteur, Prometheus, Loki, runner).
Limite assumée : le runner, lui, peut recréer des conteneurs ; un attaquant maîtrisant le runner
pourrait perturber la plateforme (redémarrages), mais pas en sortir ni modifier les images.

## 8. Commandes

```bash
cd infra && docker compose up -d --build ansible-runner remediation-engine supervision   # démarrage
docker compose logs -f remediation-engine                                                # chronologie JSON
curl -s http://localhost:8080/supervision/api/state | python -m json.tool                 # état consolidé
python ml/detection/scenarios/inject.py outage --service api --mode pause --duration 90   # répétition
```

Dashboard : http://localhost:8080/supervision/ (lecture seule). Tests : `python -m pytest services/remediation/app/tests`.
