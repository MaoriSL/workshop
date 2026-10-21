# Dossier sécurité — Poupal (pilier CYBER)

Plateforme de paiement **fictive** (démonstrateur Resilience-Alpha). Ce document couvre l'offensif
(console d'attaque + scénarios) et le défensif (WAF, SIEM, durcissement, secrets), et le **périmètre**
de confinement. Objectif : produire des incidents réalistes, observables et reproductibles que nos
défenses détectent et que le système répare tout seul (chaîne détection → remédiation → preuve).

## 0. Périmètre et règles de confinement (règle absolue)

Les attaques ne visent QUE notre SI fictif, sur nos machines, sur le réseau privé du laboratoire.
Jamais le réseau du campus, un autre groupe, un service tiers ou Internet. C'est **implémenté**, pas
seulement écrit :

- La cible est fixée par configuration (`TARGET_URL` = la gateway/WAF de notre plateforme).
- L'orchestrateur (`security/attack-console/orchestrator/app/target.py`) **refuse de lancer** toute
  attaque si la cible ne résout pas vers `localhost` ou une plage **privée** (RFC 1918, lien local,
  boucle locale, + `ATTACK_ALLOWED_CIDRS`). Une IP publique est rejetée ; la console passe en mode
  « hors périmètre » et désactive tous les boutons Lancer. Testé (`test_target.py`).
- Bandeau permanent « Laboratoire fictif — attaques limitées à notre plateforme » et bouton
  **ARRÊT D'URGENCE** global qui coupe immédiatement toute attaque (`POST /api/stop-all`).
- Intensité et durée **bornées** côté serveur (`scenarios/base.py` : concurrence ≤ 50, débit ≤ 200/s,
  durée ≤ 180 s), quelle que soit la valeur envoyée par l'interface.

## 1. Console d'attaque (`security/attack-console/`)

Interface React (lecture/contrôle, aucune commande libre) + orchestrateur FastAPI. L'orchestrateur
n'exécute QUE les scénarios de la **liste blanche** `scenarios/`, avec des paramètres validés et bornés.
À chaque lancement/arrêt, il écrit la fenêtre de l'attaque dans `ml/data/labels.csv` (type, intensité) :
les attaques deviennent des données **étiquetées** pour évaluer et réentraîner le modèle de détection.
Journal horodaté exportable en CSV (`/api/journal.csv`).

## 2. Scénarios — effet attendu, défense, remédiation

Chaque scénario produit un effet visible dans la supervision et correspond à un type d'incident que le
détecteur et le moteur de remédiation savent traiter.

| Scénario | Effet attendu | Défense | Remédiation attendue | Détecté par |
|---|---|---|---|---|
| **DoS contrôlé** (`dos`) | latence + erreurs ↑ | limitation de débit (429) gateway | blocage IP + redémarrage | ML « surcharge » |
| **Brute-force** (`bruteforce`) | rafale d'échecs 401 puis 429 | limitation /auth/login | blocage IP + remise en état auth | ML « bruteforce » + SIEM |
| **Injection** (`injection`) SQLi/XSS/traversée | requêtes **bloquées (403)** | WAF (CRS OWASP) ; API en requêtes paramétrées | tracé SIEM (pas d'impact métier) | WAF + SIEM |
| **Exfiltration** (`exfiltration`) | pic de lecture, pagination abusive | pagination plafonnée côté API | tracé SIEM | SIEM (volume) |
| **Combiné** (`combo`) | reconnaissance → brute-force | enchaînement complet | chaîne complète (démo 60 s) | ML + SIEM |

Les charges d'injection sont des chaînes de test standard (catalogues OWASP) : on **démontre que la
défense fonctionne** (l'API utilise déjà des requêtes paramétrées via l'ORM, et le WAF bloque en amont).
Aucune donnée réelle, aucune persistance de charge après l'arrêt.

## 3. WAF (`security/waf/`) — ModSecurity + CRS OWASP

Image `owasp/modsecurity-crs:nginx-alpine` (épinglée par digest), placée **devant la gateway** comme
seul point d'entrée public. Elle inspecte le trafic, bloque les injections (403) et journalise chaque
blocage (repris par Alloy → Loki → SIEM). La gateway passe sur le réseau interne.

- **Anti-faux-positifs** : le trafic normal (générateur de trafic, front) transite par le WAF ; mesuré
  sans blocage en régime nominal (`exclusions.conf` lève seulement des règles trop strictes sur des
  routes légitimes connues — jamais les règles d'injection). Vérifié : `/`, login, dashboard = 200.
- **Anti-usurpation d'IP** : le WAF voit l'IP réelle du client et la transmet. La gateway ne fait
  confiance à `X-Forwarded-For` que depuis le sous-réseau du WAF et **sans récursion** (elle prend le
  dernier saut, ajouté par le WAF), donc un attaquant ne peut pas injecter une IP pour faire bloquer
  un tiers. Vérifié : un `X-Forwarded-For: 203.0.113.99` forgé est ignoré.
- Résultats de test : injections SQLi / XSS / traversée de chemin → **403** ; trafic normal → **200**.

## 4. SIEM / corrélation (`security/siem/`)

Pas d'Elastic Stack (budget RAM du PC Hôte) : une fonction SIEM intégrée à la supervision existante.
Les événements de sécurité sont déjà en JSON dans Loki. Un petit **corrélateur** Python
(`correlator/`) évalue des règles toutes les 10 s et expose métriques + alertes ; il **observe et
corrèle, il n'agit pas** (l'action reste au moteur de remédiation).

| Règle | Motif (LogQL) | Seuil | Incident | Sévérité |
|---|---|---|---|---|
| `bruteforce_login` | échecs + limitations de connexion par IP / min | 10 | bruteforce | haute |
| `waf_block_burst` | blocages WAF (ModSecurity) par IP / min | 8 | injection | haute |
| `enumeration` | 404 sur `/api/transactions/{id}` par IP / min | 30 | exfiltration | moyenne |
| `rate_limited_burst` | réponses 429 par IP / min | 20 | surcharge | moyenne |

Seuils réglés pour ne pas se déclencher sur le trafic normal (générateur) mais sur les attaques.
Dashboard **Grafana « Poupal — Sécurité »** : alertes actives, sources en alerte par règle, événements
de sécurité / min, flux des alertes de corrélation, blocages WAF et actions de remédiation — lisible à
distance et lié visuellement aux incidents. Vérifié : un balayage d'injections + brute-force lève
`waf_block_burst`, `bruteforce_login` et `rate_limited_burst` avec la bonne IP source.

## 5. Durcissement (`security/hardening/`)

Checklist (ce qui est fait ✓ / hors périmètre d'un prototype 4 jours ⧖) :

- ✓ **Conteneurs non-root** : tous nos services applicatifs tournent en uid 10001 (Dockerfiles).
- ✓ **`no-new-privileges`** sur tous les conteneurs (aucune élévation de privilège possible).
- ✓ **`cap_drop: ALL`** sur les services Python (aucune capability Linux nécessaire en non-root).
- ✓ **Segmentation réseau** : trois réseaux (`edge`, `backend`, `monitoring`) + `console` ; la base de
  données n'est que sur `backend`, jamais exposée ; seul le WAF publie un port sur l'hôte ; Grafana et
  Prometheus sur `127.0.0.1` uniquement.
- ✓ **Images à tag/digest précis** (reproductibilité), limites mémoire par conteneur.
- ✓ **Accès Docker maîtrisé** : l'automatisation passe par un proxy du socket en liste blanche
  (`docker-socket-proxy-ansible`), jamais le socket complet ; le moteur de remédiation n'a **aucune**
  interface d'administration et ne parle qu'au runner (voir `docs/remediation.md`, analyse de sécurité).
- ✓ **Moindre privilège SQL** : deux rôles applicatifs (`poupal_auth`, `poupal_api`) + un rôle
  `poupal_exporter` en lecture seule ; l'API ne voit du schéma `auth` que la vue annuaire.
- ⧖ **Système de fichiers en lecture seule** (`read_only: true`) : non généralisé (plusieurs images
  écrivent dans /tmp, /var/run, /var/lib) ; appliqué de façon ciblée serait un durcissement
  supplémentaire pour la mise en production.
- ⧖ **Secrets runtime via agent** (Vault dynamique) : hors périmètre ; voir §6 (SOPS).

Vérification : aucune porte d'accès privilégiée « pour simplifier » n'a été laissée (le moteur n'expose
que `/api/state|incidents|events` en lecture via la gateway ; `POST /incidents` exige la signature HMAC
et n'est pas routé vers l'extérieur).

## 6. Gestion des secrets (`security/secrets/`) — SOPS + age

Choix : **SOPS + age** plutôt que Vault. Justification : Vault impose un **service** à faire tourner
(coût RAM sur le PC Hôte qui héberge déjà la plateforme, la supervision et éventuellement un LLM) ;
SOPS chiffre des **fichiers** (aucun service), ce qui convient au budget et reste simple à expliquer.

- Les secrets (mots de passe de base, secret HMAC, jeton du runner, mot de passe du générateur) sont
  chiffrés dans `security/secrets/poupal.sops.env` (commitable **car chiffré**, AES-256-GCM par clé age).
- La clé **privée** age est dans `secrets/age/keys.txt`, **hors Git** (dossier `secrets/` gitignored).
- `scripts/secrets.sh decrypt` produit `infra/.env` (gitignored) au déploiement ; `encrypt` / `edit`
  pour modifier. Tout passe par une image utilitaire (SOPS + age), rien à installer sur l'hôte.
- Les clés JWT (RS256) restent générées localement par `scripts/gen_keys.sh` dans `secrets/` (hors Git)
  et montées en lecture seule ; le module unique de lecture des secrets de chaque service
  (`core/secrets.py`) lit ces fichiers et les variables d'environnement issues de SOPS.
- **Contrôle « aucun secret en clair »** : `scripts/scan_secrets.sh` (gitleaks en conteneur, config
  `.gitleaks.toml`) à lancer en pre-commit et avant l'archive de rendu ; le fichier SOPS et les clés
  publiques sont en liste d'autorisation (ce ne sont pas des secrets en clair).

## 7. Intégration avec la détection (pilier IA)

Chaque attaque lancée depuis la console écrit sa fenêtre dans `ml/data/labels.csv`. Après plusieurs
lancements, réévaluer / réentraîner : `python -m ml.detection.evaluate` (et `train` si besoin). Le
brute-force et le DoS sont détectés par le modèle ML (« bruteforce » / « surcharge ») ; l'injection est
bloquée par le WAF et tracée par le SIEM ; l'exfiltration est un pic de lecture tracé par le SIEM. La
chaîne complète (attaque → détection → remédiation → **transaction de preuve**) est démontrée en moins
de 45 s (voir `docs/remediation.md` et la répétition ci-dessous).
