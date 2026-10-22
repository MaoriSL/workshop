\# CLAUDE.md — PROJECT RESILIENCE-ALPHA (Poupal)



\## Le projet

Démonstrateur de cyber-résilience pour le Workshop Bac+5 EPSI (Resilience-Alpha).

Objectif : prouver qu'un SI de paiement critique peut encaisser une attaque et se

rétablir \*\*sans intervention humaine\*\*. La plateforme de paiement « Poupal » est

\*\*entièrement fictive\*\* : marque inventée, données simulées, aucun paiement réel.



\## Règles d'or (ne jamais enfreindre)

\- \*\*Tout est fictif\*\* : aucune donnée bancaire ou personnelle réelle, aucune connexion à

&#x20; un vrai service de paiement. Afficher partout la mention « environnement de démonstration ».

\- \*\*Aucun secret en clair\*\* : jamais de mot de passe, clé ou token dans le code ou dans Git.

&#x20; `.env` est gitignored ; les secrets passent par Vault ou SOPS.

\- \*\*Détection par ML\*\*, pas par seuils codés en dur (`if cpu > 90`). Le modèle apprend le

&#x20; comportement normal et repère l'écart.

\- \*\*Remédiation automatique (zero-touch)\*\* : aucune action humaine pendant l'incident.

&#x20; Une intervention manuelle en démo = 0/5. Un conteneur qui redémarre ne suffit pas :

&#x20; la preuve, c'est une \*\*nouvelle transaction qui réussit\*\* après l'incident.

\- \*\*Attaques confinées\*\* : uniquement sur nos machines (PC Hôte / PC Attaquant) sur le

&#x20; réseau RESILIENCE-G<n>. Jamais le réseau du campus, un autre groupe ou Internet.

\- \*\*5 piliers interconnectés\*\* : DEV, INFRA, IA/DATA, CYBER, TRANSFORMATION. Chaque brique

&#x20; doit se brancher aux autres, pas vivre isolée.



\## Architecture (monorepo)

&#x20;   frontend/

&#x20;     poupal/        # site de paiement Poupal (vitrine + espace client)

&#x20;     supervision/   # dashboard de supervision (état services, alertes, reprise)

&#x20;   services/

&#x20;     api/           # API métier de paiement (transactions)

&#x20;     auth/          # service d'authentification (JWT)

&#x20;     remediation/   # moteur de remédiation automatique (zero-touch)

&#x20;   ml/

&#x20;     detection/     # détection d'anomalies (ML sur métriques / logs)

&#x20;     assistant/     # assistant RAG local (Ollama + LangChain)

&#x20;   infra/           # docker-compose, playbooks Ansible, Prometheus / Grafana / Loki

&#x20;   security/        # Red Team (attaques), WAF, SIEM, durcissement

&#x20;   governance/      # EBIOS RM, PCA/PRA, NIS2/DORA, recommandations

&#x20;   docs/            # dossier d'ingénierie, doc d'API, schémas



\## Stack imposée par le sujet

\- Front : React + Tailwind CSS (TypeScript, Vite).

\- Services : Node.js, Python/FastAPI ou Go — API REST ou gRPC.

\- Conteneurs : Docker Compose ; automatisation : Ansible.

\- Observabilité : Prometheus (métriques), Grafana (visualisation), Loki (logs).

\- IA : détection d'anomalies (ML) + assistant RAG local Ollama + LangChain (modèle ≤ 8 Mds params).

\- Cyber : WAF, SIEM / SOC, durcissement, gestion des secrets (Vault ou SOPS).

\- Gouvernance : EBIOS RM, PCA/PRA, conformité NIS2 / DORA.



\## Conventions de code

\- Code \*\*simple et lisible\*\* : le jury lit le code et chacun doit pouvoir l'expliquer,

&#x20; y compris le code généré par IA. Pas de magie inutile.

\- TypeScript côté front ; typage / annotations côté services quand c'est pertinent.

\- Couche réseau centralisée côté front (`src/api/`), base URL via `VITE\_API\_URL`.

\- Chaque service a son README (lancement + interfaces exposées).

\- Commits clairs et atomiques (format conventionnel : `feat:`, `fix:`, `docs:`…).

&#x20; Jamais de secret ni de donnée réelle dans un commit.



\## Commandes utiles

\- Pré-requis back (une seule fois) : `cp infra/.env.example infra/.env` (adapter les mots de passe fictifs) puis `scripts/gen\_keys.sh` (paire de clés RSA pour les JWT dans `secrets/`, dossier ignoré par Git)

\- Plateforme sans console d'attaque : `cd infra \&\& docker compose up -d --build` → http://localhost:8080 (port modifiable via `GATEWAY\_PORT` dans infra/.env si 8080 est déjà occupé) ; console optionnelle : `docker compose --profile attack up -d --build attack-orchestrator attack-console` ; arrêt : `docker compose down` (ajouter `-v` pour repartir d'une base vide et rejouer l'init SQL)

\- Données de démo : automatiques au démarrage si `SEED\_DEMO\_DATA=true` dans infra/.env (6 comptes `@poupal.demo`, mot de passe commun `DEMO\_PASSWORD`) ; relance manuelle : `scripts/seed.sh`

\- Smoke test de bout en bout (login → virement → solde → cohérence) : `python scripts/smoke\_test.py` (base http://localhost:8080 par défaut ; mot de passe lu dans `SMOKE\_PASSWORD` ou `DEMO\_PASSWORD`) — réutilisé par la remédiation comme preuve de reprise

\- Tests back (pytest dans les images, base `poupal\_test`) : `scripts/run\_tests.sh`

\- Doc d'API : contrat dans `docs/api/contract.md` ; régénérer les OpenAPI après tout changement de schéma ou de route : `python scripts/export\_openapi.py` ; Swagger en direct : http://localhost:8080/auth/docs et http://localhost:8080/api/docs

\- Logs JSON d'un service : `cd infra \&\& docker compose logs -f api` (ou `auth`, `gateway`, `db`) ; état des conteneurs : `docker compose ps`

\- Front Poupal en dev (hors Docker) : `cd frontend/poupal \&\& npm install \&\& npm run dev` avec `VITE\_API\_URL=http://localhost:8080` dans `frontend/poupal/.env` (vide = données factices)

\- Supervision : Grafana http://localhost:3000 (admin / `GRAFANA\_ADMIN\_PASSWORD`), Prometheus http://localhost:9090 (127.0.0.1 uniquement) ; dashboards provisionnés dans `infra/grafana/dashboards/` ; logs dans Grafana → Explore → Loki (`{service="poupal-api"} | json`)

\- Générateur de trafic normal : activé par `TRAFFIC\_ENABLED=true` dans infra/.env (`TRAFFIC\_USERS`, `TRAFFIC\_INTENSITY`) ; `docker compose logs -f traffic-gen`

\- Export des métriques pour le ML : `python scripts/export\_metrics.py --since 2h --step 5s` → `ml/data/metrics-*.csv`

\- Détection ML : scénarios étiquetés `python ml/detection/scenarios/inject.py outage|overload|bruteforce|db\_slow` ; entraînement `python -m ml.detection.train` ; évaluation `python -m ml.detection.evaluate` (graphiques dans `ml/detection/reports/`) ; rechargement `cd infra \&\& docker compose restart anomaly-detector` ; état en direct : dashboard « Poupal — Détection » ou `docker compose exec anomaly-detector python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8010/status').read().decode())"`

\- Playbooks Ansible (conteneur `ansible-runner`, accès Docker via proxy restreint) : `infra/ansible/run.ps1 restart\_service -e service=api` (PowerShell) ou `infra/ansible/run.sh verify` (WSL2) ; liste : deploy, restart\_service, recreate\_service, rollback, backup\_db, restore\_db, block\_ip, unblock\_ip, verify

\- Remédiation zero-touch : moteur `remediation-engine` (reçoit les incidents signés du détecteur, exécute les playbooks via `ansible-runner`, prouve la reprise par une nouvelle transaction) ; état : `curl http://localhost:8080/supervision/api/state` ; logs : `docker compose logs -f remediation-engine` ; runbook : `docs/remediation.md` ; tests : `python -m pytest services/remediation/app/tests`

\- Dashboard de supervision (lecture de l'état, avec déblocage explicite des IP bannies) : http://localhost:8080/supervision/ ; répétition générale : `python ml/detection/scenarios/inject.py outage --service api --mode pause --duration 90` puis observer détection → action → transaction de preuve → RÉTABLI

\- Secrets (SOPS + age) : `scripts/secrets.sh decrypt` déchiffre `security/secrets/poupal.sops.env` vers `infra/.env` avant tout démarrage ; `encrypt` / `edit` pour modifier ; clé privée dans `secrets/age/keys.txt` (hors Git). Contrôle « aucun secret en clair » : `scripts/scan\_secrets.sh` (gitleaks)

\- WAF : ModSecurity + CRS OWASP devant la gateway (seul port publié) ; blocages tracés dans Loki. Test : injection → 403, trafic normal → 200 (`docs/security.md` §3)

\- SIEM (corrélation) : service `siem` (lecture seule Loki) ; alertes `curl http://localhost:8080/... ` via Grafana → dashboard « Poupal — Sécurité » ; `docker compose logs -f siem`

\- Console d'attaque (PC Attaquant, laboratoire fictif) : http://localhost:8092 ; refuse toute cible hors plage privée ; scénarios dos / bruteforce / injection / exfiltration / combo ; chaque attaque s'étiquette dans `ml/data/labels.csv` ; arrêt d'urgence global. Runbook : `docs/security.md`

\- Déploiement automatisé : `cd infra \&\& ansible-playbook playbooks/deploy.yml`



\## Marque Poupal

\- Marque fictive, inventée pour l'exercice — ne reproduire aucun logo / charte d'une marque réelle.

\- Logos dans `frontend/poupal/public/` : `logo-poupal.png`, `logo-poupal-white.png`.

\- Style fintech moderne, épuré, rassurant.

\- Palette : fond `#F5F7FB`, primaire `#1B3A8B`, CTA `#2E6BFF`, texte `#10193A`, succès `#16A34A`.

\- Typo : Montserrat.



\## Livrables (dossier Workshop2026-M2-G<n>)

\- `...-Dossier.pdf` — dossier d'ingénierie et de gouvernance (8–12 pages hors annexes).

\- `...-Pres.pptx` — support de présentation.

\- `...-VidChrono.mp4` — 60 s sans coupe (attaque → détection → reprise → vérification).

\- `...-Code.zip` — archive du dépôt Git, README inclus, aucun secret en clair.

\- Gel du code jeudi 17 h, rendus avant 23 h 59.
