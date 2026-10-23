# Poupal — Resilience-Alpha

Démonstrateur de cyber-résilience pour le Workshop Bac+5 EPSI. Poupal est une
plateforme de paiement **entièrement fictive** : les comptes, utilisateurs et
transactions sont simulés. Aucun paiement réel, aucune donnée bancaire réelle
et aucun service tiers ne sont utilisés.

L'objectif est de démontrer qu'une plateforme critique peut :

1. fonctionner normalement ;
2. subir une attaque confinée au laboratoire ;
3. détecter l'anomalie par ML ;
4. déclencher une remédiation automatique sans intervention humaine ;
5. prouver sa reprise par une nouvelle transaction réussie.

## Architecture

```text
PC hôte Poupal
├── WAF ModSecurity + CRS OWASP
├── Gateway Nginx
├── Frontend Poupal
├── Authentification JWT
├── API de paiement
├── PostgreSQL
├── Détection ML
├── Remédiation zero-touch + Ansible
├── Supervision React
├── Prometheus / Grafana / Loki / SIEM
└── Assistant RAG
       └── Ollama + Qwen sur le PC d'un membre du groupe

PC attaquant (optionnel)
└── Console d'attaque + orchestrateur
```

La gateway est le point d'entrée de l'application. Le WAF est le seul
conteneur exposé sur le réseau. Les services internes ne publient pas leurs
ports directement sur l'hôte.

## Pré-requis

- Docker et Docker Compose ;
- Git ;
- Bash ou WSL2 pour les scripts shell ;
- environ 2 Go de mémoire disponible pour la plateforme complète ;
- pour le RAG : un PC accessible sur le réseau privé avec Ollama et un modèle
  compatible, par exemple `qwen3:4b`.

Toutes les attaques doivent rester limitées aux machines du laboratoire et au
réseau privé de démonstration.

## Installation

Depuis la racine du dépôt :

```bash
cp infra/.env.example infra/.env
scripts/gen_keys.sh
```

Adapter ensuite `infra/.env` avec les valeurs fictives nécessaires. Ne jamais
committer `infra/.env`, de clé privée, de mot de passe ou de token.

Si le port `8080` est occupé, modifier par exemple :

```env
GATEWAY_PORT=18080
```

Le port utilisé par les autres machines doit être autorisé par le pare-feu du
PC hôte.

## Démarrage standard

La commande suivante démarre la plateforme sans la console d'attaque :

```bash
cd infra
docker compose up -d --build
docker compose ps
```

Les services principaux doivent finir dans un état `healthy`.

URLs locales par défaut :

| Fonction | URL |
|---|---|
| Application Poupal | `http://localhost:${GATEWAY_PORT:-8080}/` |
| Supervision | `http://localhost:${GATEWAY_PORT:-8080}/supervision/` |
| Grafana | `http://localhost:${GRAFANA_PORT:-3000}/` |
| Prometheus | `http://localhost:${PROMETHEUS_PORT:-9090}/` |

Grafana et Prometheus sont liés à `127.0.0.1` par défaut. Seule la gateway
est destinée à être accessible depuis le réseau du groupe.

Arrêter la plateforme sans supprimer les données :

```bash
cd infra
docker compose down
```

`docker compose down -v` supprime les volumes, notamment la base de données.
À utiliser uniquement si les données de démonstration peuvent être recréées.

## Console d'attaque optionnelle

La console d'attaque n'est pas démarrée par la commande standard. Sur le PC
attaquant, depuis une copie du dépôt :

```bash
cd infra
docker compose --profile attack up -d --build attack-orchestrator attack-console
```

Ouvrir ensuite `http://localhost:8092`. Dans le champ cible, saisir l'adresse
privée du PC hôte, avec son port publié, par exemple :

```text
http://192.168.1.20:18080
```

L'orchestrateur refuse les cibles publiques, les URL avec identifiants,
paramètres ou fragments, et les cibles hors périmètre autorisé.

Arrêter uniquement la console :

```bash
docker compose --profile attack stop attack-console attack-orchestrator
```

Scénarios disponibles : déni de service contrôlé, brute-force, injection,
exfiltration et scénario combiné. Ils sont fictifs, bornés et destinés
uniquement à la démonstration sur la plateforme Poupal.

## Trafic normal automatique

`traffic-gen` simule des utilisateurs fictifs et produit des consultations et
des virements internes afin d'alimenter les métriques ML.

Arrêt immédiat des requêtes automatiques :

```bash
cd infra
docker compose stop traffic-gen
```

Mise en veille sans supprimer le conteneur :

```env
TRAFFIC_ENABLED=false
```

Puis appliquer la configuration :

```bash
docker compose up -d traffic-gen
```

Relancer avec la configuration existante :

```bash
docker compose start traffic-gen
```

Le générateur utilise uniquement les comptes fictifs `@poupal.demo` et ne
contacte aucun service de paiement réel.

## Assistant RAG et Ollama distant

Dans `infra/.env`, configurer l'adresse privée du PC hébergeant Ollama :

```env
OLLAMA_BASE_URL=http://10.60.12.66:11434
OLLAMA_MODEL=qwen3:4b
```

Le port Ollama doit être limité au réseau privé de la démonstration.

Le service RAG est accessible dans la supervision via l'onglet **Assistant
RAG**. Il peut aussi être vérifié avec :

```bash
curl http://localhost:${GATEWAY_PORT:-8080}/assistant/health
curl http://localhost:${GATEWAY_PORT:-8080}/assistant/ready
```

Le RAG répond à partir des documents du dépôt et peut produire un résumé
structuré d'un incident : détection, confinement, actions, rétablissement et
transaction de preuve.

## Démonstration de résilience

1. Démarrer la plateforme.
2. Ouvrir la supervision et Grafana.
3. Laisser éventuellement `traffic-gen` produire le comportement normal.
4. Depuis la console d'attaque, sélectionner une cible privée et lancer un
   scénario borné.
5. Observer la détection ML.
6. Observer l'action automatique du moteur de remédiation.
7. Vérifier la nouvelle transaction de preuve.
8. Consulter le résumé de l'incident dans l'onglet **Assistant RAG**.
9. Consulter les IP bannies et, si nécessaire, utiliser **Débannir**.

Répétition contrôlée d'une panne API :

```bash
python ml/detection/scenarios/inject.py outage \
  --service api --mode pause --duration 90
```

La preuve attendue n'est pas seulement le redémarrage d'un conteneur : une
nouvelle transaction doit réussir après la reprise.

## Transactions interrompues

Les virements utilisent obligatoirement un en-tête `Idempotency-Key`.
L'application cliente réessaie automatiquement une requête interrompue avec
la même clé pendant une durée bornée.

Cela couvre deux cas :

- la requête n'a pas été exécutée avant l'attaque ;
- le virement a été validé mais la réponse a été perdue.

Dans les deux cas, le rejeu ne crée pas de double débit. Une même clé avec un
corps différent est refusée par l'API.

## Vérifications utiles

État des services :

```bash
cd infra
docker compose ps
```

Logs :

```bash
docker compose logs -f gateway
docker compose logs -f remediation-engine
docker compose logs -f traffic-gen
```

Test de bout en bout :

```bash
python scripts/smoke_test.py
```

Tests backend :

```bash
scripts/run_tests.sh
```

Tests du moteur de remédiation :

```bash
python -m pytest services/remediation/app/tests
```

Contrôle des secrets :

```bash
scripts/scan_secrets.sh
```

## Documentation détaillée

| Sujet | Documentation |
|---|---|
| Installation et infrastructure | [`infra/README.md`](infra/README.md) |
| API métier | [`services/api/README.md`](services/api/README.md) |
| Authentification | [`services/auth/README.md`](services/auth/README.md) |
| Contrat API | [`docs/api/contract.md`](docs/api/contract.md) |
| RAG | [`docs/assistant.md`](docs/assistant.md) |
| Remédiation zero-touch | [`docs/remediation.md`](docs/remediation.md) |
| Sécurité et console d'attaque | [`docs/security.md`](docs/security.md) |
| Dashboard de supervision | [`frontend/supervision/README.md`](frontend/supervision/README.md) |
| Générateur de trafic | [`tools/traffic-gen/README.md`](tools/traffic-gen/README.md) |
| Playbooks Ansible | [`infra/ansible/README.md`](infra/ansible/README.md) |
| Gestion des secrets | [`security/secrets/README.md`](security/secrets/README.md) |

## Règles de contribution

- utiliser uniquement des données fictives ;
- ne jamais ajouter de secret en clair ;
- conserver les attaques confinées au laboratoire ;
- privilégier le code simple et explicable ;
- utiliser des commits atomiques au format conventionnel :
  `feat:`, `fix:`, `docs:`, etc. ;
- mettre à jour la documentation lors d'une modification de commande,
  d'endpoint ou de procédure de démonstration.

