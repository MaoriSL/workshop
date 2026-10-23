# Poupal — API métier de paiement (`services/api`)

Service FastAPI qui gère les **comptes** et les **transactions** de la plateforme fictive Poupal
(environnement de démonstration : aucun paiement réel, aucune donnée personnelle réelle).

## Rôle et garanties

- Montants stockés en **centimes** (entiers), devise EUR. Jamais de flottant.
- Virement = **une transaction SQL atomique** : les deux comptes sont verrouillés
  (`SELECT … FOR UPDATE`) dans l'ordre de leur identifiant, puis débit, crédit et
  enregistrement de la transaction. Un solde ne devient jamais négatif (contrôle dans le
  code **et** contrainte `CHECK` en base).
- Un solde insuffisant laisse une trace : transaction `failed` avec `failure_reason`.
- **Idempotence** : l'en-tête `Idempotency-Key` est obligatoire sur `POST /api/transactions`.
  Une même clé rejouée avec le même corps renvoie la même transaction (200) ; avec un corps
  différent, elle est refusée (422).
- En cas de coupure pendant un virement, le frontend réessaie automatiquement avec la même
  clé pendant une durée bornée. Cela permet de récupérer une transaction déjà validée ou de
  la terminer après le rétablissement de l'API, sans double débit.
- Les jetons JWT (RS256) sont vérifiés avec la **clé publique uniquement** : l'API ne peut
  pas en émettre et n'accède jamais à la table des utilisateurs du service auth.
- Les destinataires sont résolus via la vue en lecture seule `auth.user_directory`
  (voir `docs/api/database-roles.md`).

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/accounts/me` | Solde et devise (compte créé au premier appel, solde de démo) |
| GET | `/api/transactions?limit=&offset=` | Historique paginé (envoyées + reçues) |
| GET | `/api/transactions/{id}` | Détail (404 si l'utilisateur n'est pas concerné) |
| POST | `/api/transactions` | Virement (`recipient_email`, `amount_cents`, `message`) |
| GET | `/health` · `/ready` · `/metrics` | Liveness, readiness (base + clé publique), Prometheus |
| GET | `/internal/consistency` | Cohérence des soldes — réseau Docker uniquement, bloqué par la gateway |

Le contrat complet (exemples, codes d'erreur, correspondance avec le front) est dans
[`docs/api/contract.md`](../../docs/api/contract.md) ; le schéma OpenAPI exporté dans
`docs/api/api-openapi.json` (Swagger en direct : `http://localhost:8080/api/docs`).

## Structure

```
app/
  main.py              application FastAPI (CORS, middleware, handlers, routeurs)
  deps.py              utilisateur courant à partir du JWT (clé publique)
  models.py            ORM : Account, Transaction, IdempotencyKey, vue UserDirectory
  schemas.py           modèles Pydantic (entrées / sorties)
  seed.py              données de démonstration (comptes + historique)
  core/
    settings.py        configuration (variables d'environnement)
    secrets.py         lecture de la clé publique JWT (point unique, futur Vault/SOPS)
    database.py        moteur et sessions SQLAlchemy
    logging.py         logs JSON + contexte de requête
    middleware.py      X-Request-ID, métriques HTTP, log d'accès
    metrics.py         métriques Prometheus (HTTP + métier)
    rate_limit.py      limitation de débit en mémoire
    errors.py          format d'erreur unique { message, code }
  routers/             accounts.py, transactions.py, internal.py, tech.py
  services/            accounts.py (création de compte), transfer.py (virement atomique)
alembic/               migrations du schéma payments
tests/                 pytest (base poupal_test)
```

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `DATABASE_URL` | URL SQLAlchemy du rôle `poupal_api` | — (obligatoire) |
| `JWT_PUBLIC_KEY_PATH` | clé publique RSA (vérification des jetons) | `/run/secrets/jwt_public.pem` |
| `JWT_ISSUER` | émetteur attendu dans les jetons | `poupal-auth` |
| `CORS_ORIGINS` | origines autorisées (séparées par des virgules) | `http://localhost:8080` |
| `TRANSACTION_RATE_LIMIT` | virements par utilisateur, `n/secondes` | `10/60` |
| `MAX_TRANSACTION_CENTS` | plafond d'un virement | `500000` (5 000 €) |
| `DEMO_INITIAL_BALANCE_CENTS` | solde offert à la création d'un compte | `100000` |
| `SEED_DEMO_DATA` | insérer les données de démo au démarrage | `false` |
| `LOG_LEVEL` | niveau de log | `INFO` |

## Données de démonstration

Le seed (`SEED_DEMO_DATA=true`) crée les comptes des 10 utilisateurs fictifs `@poupal.demo`
(alex, camille, lea, nathan, julie, hugo, sophie, lucas, emma, thomas) avec des soldes d'ouverture
et un historique de 12 transactions ; le générateur de trafic (`tools/traffic-gen`) les fait vivre.

## Lancer

- **Avec la plateforme** (recommandé) : `cd infra && docker compose up -d --build`
  (migrations et seed appliqués par `entrypoint.sh`).
- **En local** : `python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt`,
  puis exporter `DATABASE_URL` et `JWT_PUBLIC_KEY_PATH`, `alembic upgrade head`,
  `uvicorn app.main:app --port 8000 --reload`.

## Observabilité

- Logs JSON sur stdout : `timestamp, level, service, request_id, user_id, event, method, route, status, latency_ms, client_ip`.
  Événements métier : `transaction_completed`, `transaction_failed`, `transaction_replayed`, `transaction_rate_limited`.
- Métriques : `http_requests_total`, `http_request_duration_seconds`, `poupal_db_errors_total`,
  `poupal_transactions_total{status}`, `poupal_transaction_amount_cents` (histogramme).
- `GET /internal/consistency` prouve, après un incident, qu'aucun solde n'est négatif et que
  la somme des soldes est conservée (ledger par compte).

## Tests

`scripts/run_tests.sh` (depuis la racine) exécute les suites auth puis api dans Docker, contre la
base `poupal_test`. Cas couverts : compte auto-créé, virement, solde insuffisant, auto-envoi,
montants invalides, destinataire inconnu, idempotence, pagination, cohérence, jetons invalides
ou expirés, et virements simultanés (soldes conservés, aucun 5xx).
