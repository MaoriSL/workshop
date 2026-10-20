# Poupal — Contrat d'API (v0.1)

> **Environnement de démonstration.** Poupal est une plateforme de paiement fictive : aucune donnée
> réelle, aucun paiement réel. Les emails `@poupal.demo`, montants et identifiants ci-dessous sont inventés.

Ce document est la référence pour brancher le front (`frontend/poupal/src/api/`), le smoke test et le
moteur de remédiation sur les deux services back. Les fichiers `auth-openapi.json` et `api-openapi.json`
(générés depuis le code, voir [README](README.md)) en sont la version machine. En cas de divergence, le
code fait foi et ce document doit être corrigé.

Sommaire : [1. Vue d'ensemble](#1-vue-densemble) · [2. Conventions](#2-conventions-communes) ·
[3. Auth](#3-service-dauthentification-auth) · [4. API métier](#4-api-métier-api) ·
[5. Endpoints techniques](#5-endpoints-techniques-par-service-hors-gateway) ·
[6. /internal/consistency](#6-get-internalconsistency--contrôle-de-cohérence-api) ·
[7. Codes d'erreur](#7-récapitulatif-des-codes-derreur) · [8. Correspondance avec le front](#8-correspondance-avec-le-front)

---

## 1. Vue d'ensemble

| Service | Adresse interne (réseau Docker) | Préfixe | Rôle |
|---|---|---|---|
| `auth` | `http://auth:8001` | `/auth` | inscription, connexion, profil ; **émet** les JWT (clé privée RSA) |
| `api` | `http://api:8000` | `/api`, `/internal` | comptes, transactions, contrôle de cohérence ; **vérifie** les JWT (clé publique seulement) |
| `gateway` (nginx) | `http://localhost:8080` | — | seul port publié sur l'hôte : `/auth/*` → auth, `/api/*` → api, le reste → front (SPA) |

Depuis le navigateur ou le poste de démo, **tout passe par la gateway** : `http://localhost:8080/auth/...`
et `http://localhost:8080/api/...`. La gateway :

- **bloque** `/internal/*` (403) : le contrôle de cohérence n'est joignable que depuis le réseau Docker ;
- **n'expose pas** `/health`, `/ready` et `/metrics` des services (réservés à Docker, Prometheus et la remédiation) ;
- laisse passer la documentation interactive générée par FastAPI : `http://localhost:8080/auth/docs`,
  `http://localhost:8080/api/docs` (JSON brut : `/auth/openapi.json`, `/api/openapi.json`).

## 2. Conventions communes

- **JSON uniquement** (`Content-Type: application/json`), clés en `snake_case`.
- **Dates** : ISO 8601 en UTC, ex. `2026-10-19T14:32:10.120344Z` (le suffixe peut être `Z` ou `+00:00` ;
  `new Date(valeur)` lit les deux).
- **Montants** : entiers en **centimes** (`amount_cents`, `balance_cents`), devise `EUR`. Jamais de nombre à
  virgule : 12,80 € = `1280`.
- **Identifiants** : UUID sous forme de chaîne (`"3f2c9e0a-6d2e-4f7a-9b1d-1c2e3f4a5b6c"`).
- **Authentification** : `Authorization: Bearer <access_token>` (JWT RS256 émis par auth, durée 30 min).
- **`X-Request-ID`** : accepté en entrée (64 caractères max), généré sinon, **toujours renvoyé** dans la
  réponse et exposé au navigateur (CORS). C'est la clé de corrélation entre front, gateway, logs et supervision.
- **CORS** : origines listées dans `CORS_ORIGINS` (`http://localhost:8080` par défaut ; ajouter
  `http://localhost:5173` pour Vite en développement) ; méthodes `GET`, `POST`, `OPTIONS` ; en-têtes autorisés
  `Authorization`, `Content-Type`, `X-Request-ID` et, sur l'api, `Idempotency-Key`.
- **Limitation de débit** : réponse `429` avec l'en-tête `Retry-After` (en secondes).

### 2.1 Format d'erreur unique

Toute réponse d'erreur (4xx / 5xx) produite par un service a cette forme :

```json
{ "message": "Email ou mot de passe incorrect.", "code": "invalid_credentials" }
```

- `message` : phrase sobre, en français, destinée à l'affichage (c'est ce que lit `src/api/client.ts`) ;
- `code` : identifiant **stable** sur lequel le front branche sa logique (ex. `insufficient_funds`).
  **Se fier à `code`, jamais au texte.** Aucun détail technique (stack trace, SQL) n'est renvoyé au client.

Cas particulier des erreurs de validation (`422`) : un tableau `errors` s'ajoute, une entrée par champ.

```json
{
  "message": "Requête invalide.",
  "code": "validation_error",
  "errors": [
    { "field": "password", "message": "String should have at least 10 characters" },
    { "field": "email", "message": "value is not a valid email address: An email address must have an @-sign." }
  ]
}
```

`field` est le chemin du champ sans le préfixe `body` (ex. `password`, ou `query.limit` → `limit`) ;
`message` est le texte produit par Pydantic (en anglais).

### 2.2 Erreurs transverses (présentes sur tous les services)

| HTTP | `code` | Quand | `message` |
|---|---|---|---|
| 401 | `invalid_token` | jeton absent, mal formé, signature invalide, expiré ou émetteur inattendu ; en-tête `WWW-Authenticate: Bearer` | « Authentification requise. » |
| 404 / 405 | `http_error` | route inconnue / méthode non autorisée (FastAPI) | « Not Found » / « Method Not Allowed » |
| 422 | `validation_error` | corps, en-tête ou paramètre invalide (+ `errors`) | « Requête invalide. » |
| 429 | `rate_limited` | limitation de débit (+ `Retry-After`) | « Trop de tentatives. Réessayez dans un instant. » |
| 500 | `internal_error` | erreur non prévue (détail uniquement dans les logs) | « Erreur interne. » |
| 503 | `database_error` | base injoignable ou erreur SQL | « Service temporairement indisponible. » |

**Note gateway** : une requête `/internal/...` venue de l'extérieur reçoit un `403` **nginx** (page HTML, pas
de JSON) ; de même une `502` / `504` nginx quand un service est arrêté (c'est précisément le cas pendant un
incident). Le client doit donc tolérer un corps non JSON — `extractErrorMessage` de `client.ts` le fait déjà
(`Erreur 502`).

## 3. Service d'authentification (`/auth`)

### 3.1 `POST /auth/register` — inscription

| Champ | Type | Règles |
|---|---|---|
| `name` | string | 2 à 80 caractères |
| `email` | string (email valide) | normalisé en **minuscules**, unique |
| `password` | string | **≥ 10 caractères** (`PASSWORD_MIN_LENGTH`) ; jamais journalisé, stocké hashé (Argon2) |

Requête :

```http
POST /auth/register HTTP/1.1
Content-Type: application/json

{ "name": "Alex Martin", "email": "Alex@Poupal.demo", "password": "exemple-mot-de-passe" }
```

Réponse `201 Created` :

```json
{
  "id": "3f2c9e0a-6d2e-4f7a-9b1d-1c2e3f4a5b6c",
  "email": "alex@poupal.demo",
  "name": "Alex Martin",
  "created_at": "2026-10-19T09:12:45.120344Z"
}
```

Erreurs :

| HTTP | `code` | `message` |
|---|---|---|
| 409 | `email_already_used` | « Un compte existe déjà avec cet email. » |
| 422 | `validation_error` | « Requête invalide. » (+ `errors` : nom trop court, email invalide, mot de passe < 10) |

L'inscription **ne renvoie pas de jeton** : enchaîner avec `POST /auth/login`. Un événement `user_registered`
est journalisé.

### 3.2 `POST /auth/login` — connexion

Corps : `{ "email": "alex@poupal.demo", "password": "..." }`.

Réponse `200 OK` :

```json
{ "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzZjJjOWUwYS0uLi4ifQ.signature", "token_type": "bearer", "expires_in": 1800 }
```

`expires_in` est en secondes (`JWT_EXPIRES_MINUTES × 60`). La réponse ne contient **aucune information
utilisateur** : appeler ensuite `GET /auth/me`.

Erreurs :

| HTTP | `code` | `message` | Note |
|---|---|---|---|
| 401 | `invalid_credentials` | « Email ou mot de passe incorrect. » | **même réponse** pour un email inconnu et un mot de passe faux (pas d'énumération de comptes) ; une vérification Argon2 factice est exécutée quand l'email est inconnu (temps de réponse constant) |
| 422 | `validation_error` | « Requête invalide. » | email mal formé, champ manquant |
| 429 | `rate_limited` | « Trop de tentatives. Réessayez dans un instant. » | **5 tentatives / 60 s par adresse IP** (`LOGIN_RATE_LIMIT`), en-tête `Retry-After` ; les tentatives réussies comptent aussi |

En démo, tous les navigateurs d'un même poste partagent l'IP, donc le compteur : 5 appels à `/auth/login`
en une minute bloquent le poste jusqu'à expiration de la fenêtre. Métrique :
`poupal_login_attempts_total{result="success"|"failure"|"rate_limited"}`.

### 3.3 `GET /auth/me` — profil de l'utilisateur connecté

En-tête `Authorization: Bearer <access_token>`. Réponse `200 OK`, même forme que l'inscription :

```json
{
  "id": "3f2c9e0a-6d2e-4f7a-9b1d-1c2e3f4a5b6c",
  "email": "alex@poupal.demo",
  "name": "Alex Martin",
  "created_at": "2026-10-19T09:12:45.120344Z"
}
```

Erreur `401` `invalid_token` « Authentification requise. » (+ `WWW-Authenticate: Bearer`) : jeton absent, mal
formé, signature invalide, expiré, ou `iss` inattendu. Le profil est relu en base : un utilisateur supprimé
obtient aussi `401`.

### 3.4 Le jeton JWT

- **RS256** : signé par `auth` avec la clé privée (`secrets/jwt_private.pem`), vérifié par `auth` et `api`
  avec la clé **publique**. L'API ne peut donc pas fabriquer de jeton, même compromise.
- Claims : `sub` (id utilisateur, chaîne UUID), `email`, `name`, `iat`, `exp` (= `iat` + 30 min),
  `iss` = `poupal-auth`.
- Vérification côté services :
  `jwt.decode(token, public_key, algorithms=["RS256"], issuer="poupal-auth", options={"require": ["exp", "iat", "sub"]})`.
- Pas de refresh token ni de révocation : après expiration, toute route protégée répond `401` ; le front
  efface le jeton (`localStorage`, clé `poupal.token`) et renvoie vers `/login`. `logout()` est purement
  client.

Payload décodé (exemple, aucune valeur de sécurité) :

```json
{
  "sub": "3f2c9e0a-6d2e-4f7a-9b1d-1c2e3f4a5b6c",
  "email": "alex@poupal.demo",
  "name": "Alex Martin",
  "iat": 1792408365,
  "exp": 1792410165,
  "iss": "poupal-auth"
}
```

## 4. API métier (`/api`)

Toutes les routes `/api/*` exigent un Bearer valide, sinon `401` `invalid_token`. L'utilisateur courant est
déduit des claims (`sub`, `email`, `name`) : **l'API ne lit jamais `auth.users`** (voir
[database-roles.md](database-roles.md)). Elle ne consulte que la vue annuaire `auth.user_directory` pour
trouver un destinataire et nommer une contrepartie.

### 4.1 `GET /api/accounts/me` — compte de l'utilisateur

Crée le compte à la première visite, avec un solde de bienvenue `DEMO_INITIAL_BALANCE_CENTS`
(100 000 centimes = 1 000,00 €) ; `opening_balance_cents` garde cette valeur pour le contrôle de cohérence.
La création est idempotente (deux appels simultanés ne créent qu'un compte).

Réponse `200 OK` :

```json
{
  "account_id": "8a1f2b3c-4d5e-4f60-8171-829394a5b6c7",
  "user_id": "3f2c9e0a-6d2e-4f7a-9b1d-1c2e3f4a5b6c",
  "balance_cents": 244900,
  "currency": "EUR",
  "opening_balance_cents": 245000,
  "created_at": "2026-10-01T08:00:00Z"
}
```

Erreurs : `401` `invalid_token`, `503` `database_error`.

### 4.2 L'objet `TransactionOut`

Toutes les routes « transactions » renvoient cet objet, toujours **relatif à l'utilisateur courant** :

| Champ | Type | Description |
|---|---|---|
| `id` | UUID | identifiant technique (à utiliser dans les URL) |
| `reference` | string | référence lisible par le client, ex. `PP-2026-000412` (séquence SQL, 6 chiffres) |
| `type` | `"sent"` \| `"received"` | sens **vu par l'utilisateur courant** : la même transaction est `sent` pour l'émetteur et `received` pour le destinataire |
| `status` | `"completed"` \| `"failed"` \| `"pending"` | `failed` = refusée (solde insuffisant), visible dans l'historique ; `pending` = en attente (données de démo uniquement) |
| `amount_cents` | int > 0 | montant **toujours positif** ; le signe se déduit de `type` |
| `currency` | string | `"EUR"` |
| `message` | string \| null | message libre, 140 caractères max |
| `failure_reason` | string \| null | `"insufficient_funds"` quand `status = "failed"`, sinon `null` |
| `counterparty` | objet | l'autre partie : destinataire si `sent`, émetteur si `received` → `{ "user_id", "email", "name" }`. Si l'utilisateur n'est plus dans l'annuaire : `"name": "Utilisateur inconnu"`, `"email": null` |
| `created_at` | datetime | date de la transaction |

```json
{
  "id": "c0ffee12-3456-4789-abcd-ef0123456789",
  "reference": "PP-2026-000412",
  "type": "sent",
  "status": "completed",
  "amount_cents": 1280,
  "currency": "EUR",
  "message": "Remboursement restaurant",
  "failure_reason": null,
  "counterparty": {
    "user_id": "7d1e5f2a-9b3c-4d6e-8f70-a1b2c3d4e5f6",
    "email": "camille@poupal.demo",
    "name": "Camille Dupont"
  },
  "created_at": "2026-10-18T14:32:00Z"
}
```

### 4.3 `GET /api/transactions` — historique

Paramètres de requête : `limit` (1 à 100, défaut 20), `offset` (≥ 0, défaut 0). Renvoie les transactions
**envoyées et reçues** par l'utilisateur, les plus récentes d'abord (`created_at` décroissant), y compris
les `failed` et `pending`.

Réponse `200 OK` :

```json
{
  "items": [
    {
      "id": "c0ffee12-3456-4789-abcd-ef0123456789",
      "reference": "PP-2026-000412",
      "type": "sent",
      "status": "completed",
      "amount_cents": 1280,
      "currency": "EUR",
      "message": "Remboursement restaurant",
      "failure_reason": null,
      "counterparty": { "user_id": "7d1e5f2a-9b3c-4d6e-8f70-a1b2c3d4e5f6", "email": "camille@poupal.demo", "name": "Camille Dupont" },
      "created_at": "2026-10-18T14:32:00Z"
    },
    {
      "id": "0b5e7a9c-1d3f-4a2b-9c8d-7e6f5a4b3c2d",
      "reference": "PP-2026-000406",
      "type": "sent",
      "status": "failed",
      "amount_cents": 30000,
      "currency": "EUR",
      "message": "Vélo d'occasion",
      "failure_reason": "insufficient_funds",
      "counterparty": { "user_id": "a9b8c7d6-e5f4-4a3b-8c2d-1e0f9a8b7c6d", "email": "hugo@poupal.demo", "name": "Hugo Garnier" },
      "created_at": "2026-10-12T20:15:00Z"
    }
  ],
  "total": 12,
  "limit": 20,
  "offset": 0
}
```

`total` est le nombre total de transactions de l'utilisateur (pour paginer). Erreur `422` `validation_error`
si `limit` ou `offset` est hors bornes.

### 4.4 `GET /api/transactions/{transaction_id}` — détail

Réponse `200 OK` : un `TransactionOut`, **uniquement** si l'utilisateur courant est émetteur ou destinataire.

Erreur `404` `transaction_not_found` « Transaction introuvable. » dans **tous** les autres cas : transaction
d'un tiers, inexistante, ou identifiant qui n'est pas un UUID. Jamais de `403` : on ne révèle pas l'existence
d'une transaction qui ne concerne pas l'appelant.

### 4.5 `POST /api/transactions` — envoyer de l'argent

En-têtes : `Authorization: Bearer ...`, `Content-Type: application/json` et
**`Idempotency-Key: <1 à 128 caractères>`** (obligatoire : un UUID v4 généré par le client pour chaque
nouvel envoi, **réutilisé tel quel** si la requête est rejouée après une coupure réseau).

| Champ | Type | Règles |
|---|---|---|
| `recipient_email` | string (email valide) | email Poupal du destinataire, insensible à la casse ; un **nom** n'est pas accepté |
| `amount_cents` | int | `> 0` et `≤ MAX_TRANSACTION_CENTS` (500 000 = 5 000,00 €) |
| `message` | string, optionnel | 140 caractères max ; `null` ou absent = pas de message |

Requête :

```http
POST /api/transactions HTTP/1.1
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Content-Type: application/json
Idempotency-Key: 6f1c7a2e-0b4d-4c8e-9f3a-2d5b8e1c4a7f

{ "recipient_email": "camille@poupal.demo", "amount_cents": 1280, "message": "Remboursement restaurant" }
```

Réponse `201 Created` : le `TransactionOut` créé, avec `type = "sent"` et `status = "completed"`
(exemple en 4.2). Le débit de l'émetteur et le crédit du destinataire sont faits dans **une seule
transaction SQL**, les deux comptes étant verrouillés dans un ordre constant : jamais de solde négatif,
jamais d'interblocage, même sous charge concurrente.

Règles, **dans l'ordre d'évaluation** (la première qui s'applique répond) :

| # | HTTP | `code` | `message` | Condition |
|---|---|---|---|---|
| 0 | 422 | `validation_error` | « Requête invalide. » (+ `errors`) | corps invalide : `amount_cents` ≤ 0 ou non entier, email mal formé, `message` > 140, champ manquant (validation Pydantic, avant toute logique métier) |
| 1 | 400 | `idempotency_key_required` | « L'en-tête Idempotency-Key est obligatoire. » (libellé indicatif) | en-tête absent ou vide |
| 2 | 429 | `rate_limited` | « Trop de tentatives. Réessayez dans un instant. » | plus de **10 envois / 60 s par utilisateur** (`TRANSACTION_RATE_LIMIT`), + `Retry-After` |
| 3a | **200** | — | *rejeu* | clé déjà utilisée par cet utilisateur avec le **même corps** : la réponse mémorisée est renvoyée à l'identique (même `TransactionOut` — en `200`, pas `201` — ou la même erreur `422` `insufficient_funds`). **Aucune seconde transaction n'est créée.** |
| 3b | 422 | `idempotency_key_reused` | « Cette clé d'idempotence a déjà servi pour une autre requête. » (libellé indicatif) | clé déjà utilisée avec un corps **différent** (empreinte SHA-256 de `{recipient_email, amount_cents, message}`) |
| 4 | 422 | `amount_too_large` | « Le montant maximal est de 5 000,00 €. » | `amount_cents` > 500 000 |
| 5 | 404 | `recipient_not_found` | « Aucun compte Poupal ne correspond à cet email. » (libellé indicatif) | email absent de l'annuaire `auth.user_directory` |
| 6 | 422 | `self_transfer` | « Vous ne pouvez pas vous envoyer de l'argent à vous-même. » (libellé indicatif) | destinataire = utilisateur courant |
| 7 | 422 | `insufficient_funds` | « Solde insuffisant. » | solde de l'émetteur < montant. Une transaction **`failed`** (`failure_reason = "insufficient_funds"`) est enregistrée et visible dans l'historique des deux utilisateurs ; la clé d'idempotence mémorise ce résultat |

Les libellés marqués *indicatif* ne sont pas figés par la spécification : le front doit s'appuyer sur `code`.
Les autres sont contractuels.

Exemple d'échec (`422`) :

```json
{ "message": "Solde insuffisant.", "code": "insufficient_funds" }
```

Effets observables : métriques `poupal_transactions_total{status="completed"|"failed"}` et
`poupal_transaction_amount_cents` ; événements de log `transaction_completed` (`transaction_id`,
`amount_cents`, `sender_id`, `recipient_id`) ou `transaction_failed` (`reason`).

### 4.6 Parcours complet en ligne de commande

Le script [`scripts/smoke_test.py`](../../scripts/smoke_test.py) (stdlib uniquement) exécute ce parcours et
sert de preuve de reprise au moteur de remédiation : `python scripts/smoke_test.py` (mot de passe via
`SMOKE_PASSWORD` ou `DEMO_PASSWORD`). Équivalent manuel avec curl :

```bash
BASE=http://localhost:8080
# 1. connexion (le mot de passe vient de l'environnement, jamais en clair dans un script)
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"alex@poupal.demo\",\"password\":\"$DEMO_PASSWORD\"}" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
# 2. solde
curl -s "$BASE/api/accounts/me" -H "Authorization: Bearer $TOKEN"
# 3. virement de 1,00 € (clé d'idempotence = UUID aléatoire)
KEY=$(python -c 'import uuid; print(uuid.uuid4())')
curl -s -X POST "$BASE/api/transactions" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H "Idempotency-Key: $KEY" \
  -d '{"recipient_email":"camille@poupal.demo","amount_cents":100,"message":"Test"}'
# 4. historique (5 dernières)
curl -s "$BASE/api/transactions?limit=5" -H "Authorization: Bearer $TOKEN"
```

## 5. Endpoints techniques (par service, hors gateway)

Disponibles sur `http://auth:8001` et `http://api:8000` **depuis le réseau Docker uniquement** (la gateway ne
les route pas). Sans authentification, sans log d'accès (pour ne pas polluer les journaux).

| Route | Réponse | Usage |
|---|---|---|
| `GET /health` | `200` `{ "status": "ok", "service": "poupal-api" }` | *liveness* : le processus répond |
| `GET /ready` | `200` si tout va bien, **`503`** sinon (corps ci-dessous) | *readiness* : base joignable (`SELECT 1`) **et** clés JWT lisibles. C'est la sonde du `HEALTHCHECK` Docker (toutes les 10 s) et le signal de la remédiation |
| `GET /metrics` | texte Prometheus (`text/plain; version=0.0.4`) | collecte par Prometheus |

Corps de `/ready` :

```json
{ "status": "ko", "service": "poupal-api", "checks": { "database": false, "secrets": true } }
```

Métriques exposées :

| Métrique | Labels | Service |
|---|---|---|
| `http_requests_total` | `service`, `method`, `route` (forme template, ex. `/api/transactions/{transaction_id}`), `status` | auth, api |
| `http_request_duration_seconds` (histogramme) | `service`, `method`, `route` | auth, api |
| `poupal_db_errors_total` | `service` | auth, api |
| `poupal_login_attempts_total` | `result` = `success` \| `failure` \| `rate_limited` | auth |
| `poupal_transactions_total` | `status` = `completed` \| `failed` \| `pending` | api |
| `poupal_transaction_amount_cents` (histogramme) | — | api |

Interroger une sonde depuis l'hôte (l'image slim n'a pas `curl`) :

```bash
cd infra && docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```

## 6. `GET /internal/consistency` — contrôle de cohérence (api)

Sans authentification, **réseau Docker uniquement** (`http://api:8000/internal/consistency` ; la gateway
répond `403`). Destiné à la supervision et au moteur de remédiation : c'est la preuve que les soldes sont
restés justes après un incident. Toujours `200` — c'est un rapport, le verdict est dans `status`.

```json
{
  "status": "ok",
  "checks": {
    "negative_balances": { "ok": true, "count": 0 },
    "total_conservation": { "ok": true, "sum_balances_cents": 1040000, "sum_opening_balances_cents": 1040000 },
    "per_account_ledger": { "ok": true, "mismatches": [] }
  },
  "checked_at": "2026-10-19T10:05:00.000412Z"
}
```

| Contrôle | Vérifie | En cas d'écart |
|---|---|---|
| `negative_balances` | aucun compte sous zéro | `count` = nombre de comptes négatifs |
| `total_conservation` | Σ `balance_cents` = Σ `opening_balance_cents` (un virement interne ne crée ni ne détruit d'argent) | les deux sommes diffèrent |
| `per_account_ledger` | pour chaque compte : `opening + Σ reçues completed − Σ envoyées completed = balance` | une entrée `{ "account_id", "expected_cents", "actual_cents" }` par compte en écart |

Exemple de rapport en échec :

```json
{
  "status": "ko",
  "checks": {
    "negative_balances": { "ok": true, "count": 0 },
    "total_conservation": { "ok": false, "sum_balances_cents": 1039500, "sum_opening_balances_cents": 1040000 },
    "per_account_ledger": {
      "ok": false,
      "mismatches": [
        { "account_id": "8a1f2b3c-4d5e-4f60-8171-829394a5b6c7", "expected_cents": 244900, "actual_cents": 244400 }
      ]
    }
  },
  "checked_at": "2026-10-19T10:06:30.004210Z"
}
```

Si la base est injoignable, le handler commun répond `503` `database_error` (le rapport n'a pas pu être établi).

## 7. Récapitulatif des codes d'erreur

| `code` | HTTP | Endpoint(s) |
|---|---|---|
| `validation_error` | 422 | tous (corps, en-tête ou paramètre invalide) |
| `invalid_token` | 401 | `GET /auth/me`, toutes les routes `/api/*` |
| `invalid_credentials` | 401 | `POST /auth/login` |
| `email_already_used` | 409 | `POST /auth/register` |
| `rate_limited` | 429 | `POST /auth/login` (par IP), `POST /api/transactions` (par utilisateur) |
| `idempotency_key_required` | 400 | `POST /api/transactions` |
| `idempotency_key_reused` | 422 | `POST /api/transactions` |
| `amount_too_large` | 422 | `POST /api/transactions` |
| `recipient_not_found` | 404 | `POST /api/transactions` |
| `self_transfer` | 422 | `POST /api/transactions` |
| `insufficient_funds` | 422 | `POST /api/transactions` |
| `transaction_not_found` | 404 | `GET /api/transactions/{transaction_id}` |
| `http_error` | 404 / 405 | route inconnue, méthode non autorisée |
| `database_error` | 503 | tous |
| `internal_error` | 500 | tous |

## 8. Correspondance avec le front

Le front (`frontend/poupal/src/api/`) est **branché** sur ce contrat : `client.ts` (base URL, jeton, erreurs
`{ message, code }`, événement `poupal:unauthorized` sur 401), `auth.ts`, `transactions.ts` et `mappers.ts`
(centimes ↔ euros, snake_case ↔ camelCase). Les types de `src/types/index.ts` restent la frontière des pages :
seule la couche `src/api/` convertit. Cette section documente ce branchement, fonction par fonction.

### 8.1 Configuration (`src/api/client.ts`)

- `VITE_API_URL` pointe sur **l'origine de la gateway, sans suffixe** (`http://localhost:8080` avec le serveur
  de dev Vite ; vide = même origine, cas du conteneur `front` derrière la gateway). Les chemins commencent par
  `/auth` et `/api` ; le port 8000 n'est jamais publié.
- `CORS_ORIGINS` (infra/.env) doit contenir `http://localhost:5173` pour que Vite puisse appeler la gateway.
- Règle du mode mock : `USE_MOCK = VITE_USE_MOCK === 'true' || (VITE_USE_MOCK !== 'false' && API_URL === '')`.
  `infra/docker-compose.yml` construit le front avec `VITE_API_URL=""` et `VITE_USE_MOCK="false"` → vrais appels,
  même origine.
- `request()` accepte des en-têtes supplémentaires (`Idempotency-Key` pour `sendMoney`) et conserve le `code`
  de l'erreur dans `ApiError` (`error.code`). Un `401` en cours de session efface le jeton et émet
  `poupal:unauthorized` : le contexte d'authentification repasse en mode déconnecté.

### 8.2 Types front ↔ objets API

| Type front (`src/types`) | Objet API | Conversion |
|---|---|---|
| `User { id, name, email, createdAt }` | `/auth/me` → `{ id, name, email, created_at }` | `createdAt = created_at` |
| `AuthResponse { token, user }` | `/auth/login` → `{ access_token }` puis `/auth/me` | construit côté client : `token = access_token` |
| `Account { balance, currency }` | `/api/accounts/me` | `balance = balance_cents / 100` |
| `Transaction` | `TransactionOut` | `counterparty = counterparty.name`, `counterpartyEmail = counterparty.email ?? undefined`, `amount = amount_cents / 100`, `date = created_at`, `message = message ?? undefined` ; `id`, `reference`, `type`, `status`, `currency` identiques |
| `SendMoneyRequest { recipient, amount, message }` | corps de `POST /api/transactions` | `recipient_email = recipient.trim().toLowerCase()`, `amount_cents = Math.round(amount * 100)`, `message = message?.trim() || undefined` |

Fonctions de conversion proposées (à placer dans `src/api/`, par exemple `mappers.ts`) :

```ts
import type { Account, Transaction, User } from '@/types'

/** Formes brutes renvoyées par l'API (snake_case, montants en centimes). */
export interface ApiUser { id: string; email: string; name: string; created_at: string }
export interface ApiAccount {
  account_id: string; user_id: string; balance_cents: number; currency: 'EUR'
  opening_balance_cents: number; created_at: string
}
export interface ApiTransaction {
  id: string; reference: string; type: 'sent' | 'received'
  status: 'completed' | 'failed' | 'pending'; amount_cents: number; currency: 'EUR'
  message: string | null; failure_reason: string | null
  counterparty: { user_id: string; email: string | null; name: string }; created_at: string
}
export interface ApiPage<T> { items: T[]; total: number; limit: number; offset: number }

export const toUser = (u: ApiUser): User => ({ id: u.id, name: u.name, email: u.email, createdAt: u.created_at })
export const toAccount = (a: ApiAccount): Account => ({ balance: a.balance_cents / 100, currency: 'EUR' })
export const toTransaction = (t: ApiTransaction): Transaction => ({
  id: t.id,
  reference: t.reference,
  type: t.type,
  status: t.status,
  counterparty: t.counterparty.name,
  counterpartyEmail: t.counterparty.email ?? undefined,
  amount: t.amount_cents / 100,
  currency: 'EUR',
  date: t.created_at,
  message: t.message ?? undefined,
})
```

### 8.3 Fonction par fonction

| Fonction front (hors mock) | Appel(s) API | Détail |
|---|---|---|
| `login({ email, password })` | `POST /auth/login` → `tokenStorage.set(access_token)` → `GET /auth/me` | retourne `{ token: access_token, user: toUser(me) }`. `401` → `ApiError(401, "Email ou mot de passe incorrect.")` ; `429` → message « Trop de tentatives… » |
| `signup({ name, email, password })` | `POST /auth/register` (`201`) puis **le même enchaînement que `login`** | `409` → « Un compte existe déjà avec cet email. ». Le back exige **10 caractères** de mot de passe : aligner la validation front (`LoginPage`, `SignupPage` : 8 aujourd'hui) |
| `getCurrentUser()` | `GET /auth/me` | inchangé : `401` → `tokenStorage.clear()` et `null` (déjà en place) |
| `logout()` | aucun appel | le jeton est effacé côté client ; pas de révocation serveur |
| `getAccount()` | `GET /api/accounts/me` | `toAccount(...)` ; crée le compte au premier appel (solde de bienvenue) |
| `listTransactions()` | `GET /api/transactions?limit=100&offset=0` | `page.items.map(toTransaction)` ; les pages gardent `Transaction[]`. `total` permet une vraie pagination plus tard |
| `getTransaction(id)` | `GET /api/transactions/${encodeURIComponent(id)}` | `toTransaction(...)` ; `404` → « Transaction introuvable. » (message déjà attendu par la page) |
| `sendMoney({ recipient, amount, message })` | `POST /api/transactions` avec `Idempotency-Key` | corps `{ recipient_email, amount_cents: Math.round(amount * 100), message }` ; `201` (ou `200` en rejeu) → `toTransaction(...)`. Clé : `crypto.randomUUID()` |

Squelette de `sendMoney` :

```ts
export async function sendMoney(data: SendMoneyRequest, idempotencyKey = crypto.randomUUID()): Promise<Transaction> {
  const raw = await request<ApiTransaction>('/api/transactions', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: {
      recipient_email: data.recipient.trim().toLowerCase(),
      amount_cents: Math.round(data.amount * 100), // 12.8 € → 1280, sans erreur d'arrondi flottant
      message: data.message?.trim() || undefined,
    },
  })
  return toTransaction(raw)
}
```

Le paramètre `idempotencyKey` permet à `SendConfirmPage` de générer **une clé par brouillon**
(`useRef(crypto.randomUUID())`) et de la réutiliser si l'utilisateur clique à nouveau sur « Confirmer »
après une erreur réseau : le back renvoie alors la transaction déjà créée au lieu d'en créer une seconde.

### 8.4 Règles métier à refléter côté front

- **Destinataire = email obligatoire.** Le champ « Email ou nom du destinataire » doit soit exiger un email
  (`isValidEmail`), soit résoudre un nom choisi dans `RecentRecipients` vers le `counterpartyEmail` de la
  transaction correspondante avant l'appel. Sinon : `422 validation_error`. Email inconnu : `404`
  `recipient_not_found` ; soi-même : `422` `self_transfer`.
- **Montant** : `parseAmount` limite déjà à deux décimales ; ajouter la borne `amount <= 5000` avec le message
  « Le montant maximal est de 5 000,00 €. » pour éviter un aller-retour (`422` `amount_too_large`).
- **Solde insuffisant** (`422` `insufficient_funds`) : la transaction `failed` apparaît ensuite dans
  l'historique avec le badge « Échouée » déjà prévu ; recharger le solde après l'erreur.
- **Mot de passe** : 10 caractères minimum (front : 8 aujourd'hui).
- **Référence** : le back produit `PP-2026-000412` (6 chiffres) là où le mock produisait `PP-2026-0412`.
- **Session** : `expires_in = 1800` s. Un `401` sur n'importe quelle route signifie « jeton expiré » : effacer le
  jeton et rediriger vers `/login` (`ProtectedRoute` + `getCurrentUser` le font déjà au rechargement).
- **Comptes de démo** (si `SEED_DEMO_DATA=true`) : `alex`, `camille`, `lea`, `nathan`, `julie`, `hugo`
  `@poupal.demo`, mot de passe commun `DEMO_PASSWORD` (infra/.env, jamais dans le code ni dans le front).

### 8.5 Ordre de branchement conseillé

1. `infra/.env` : `CORS_ORIGINS=http://localhost:8080,http://localhost:5173` ; `frontend/poupal/.env` :
   `VITE_API_URL=http://localhost:8080`.
2. `client.ts` : correctif `USE_MOCK`, option `headers`, `code` dans `ApiError`.
3. `auth.ts` : `login` / `signup` / `getCurrentUser` selon 8.3 (le mode mock reste tel quel).
4. `transactions.ts` : nouveaux chemins `/api/...`, mappers, `Idempotency-Key`.
5. Validations front : mot de passe ≥ 10, destinataire = email, montant ≤ 5 000 €.
6. Vérifier le back seul avec `python scripts/smoke_test.py`, puis le parcours complet dans le navigateur
   (inscription → connexion → solde → envoi → détail), et enfin la reconstruction Docker (`cd infra && docker compose up -d --build front`).
