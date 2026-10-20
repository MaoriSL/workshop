# Poupal — service d'authentification (`services/auth`)

> Environnement de démonstration : plateforme de paiement **fictive**, aucune donnée réelle.

## Rôle

Le service auth est la **seule** brique qui connaît les mots de passe (hachés avec Argon2)
et la **seule** qui détient la clé privée RSA servant à signer les jetons JWT (RS256).
Il expose trois routes métier : inscription, connexion, profil. L'API métier
(`services/api`) ne fait que **vérifier** les jetons avec la clé publique et lit les
utilisateurs via la vue `auth.user_directory` (id, email, name) — jamais la table `auth.users`.

```
front ──▶ gateway (nginx :8080) ──▶ /auth/* ──▶ auth :8001 ──▶ PostgreSQL (schéma auth)
                                            └── /api/*  ──▶ api :8000 (vérifie le JWT avec la clé publique)
```

Arborescence :

| Fichier | Contenu |
|---|---|
| `app/main.py` | Application FastAPI, CORS, middleware de contexte, handlers d'erreurs |
| `app/routers/auth.py` | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| `app/routers/tech.py` | `/health`, `/ready`, `/metrics` |
| `app/schemas.py` | Schémas Pydantic (validation des entrées, format des sorties) |
| `app/security.py` | Hachage Argon2, création / vérification des JWT RS256 |
| `app/deps.py` | Dépendance `get_current_user` (jeton Bearer → `User`) |
| `app/seed.py` | Les 10 utilisateurs de démonstration (`python -m app.seed`) |
| `app/models.py` | Modèle ORM `User` (table `auth.users`) |
| `app/core/` | Settings, secrets, logs JSON, middleware, métriques, limiteur de débit, base, erreurs |
| `alembic/` | Migrations du schéma `auth` (table `users`, vue `user_directory`) |

## Lancement

### Avec la plateforme complète (recommandé)

```bash
cp infra/.env.example infra/.env     # puis adapter les mots de passe (fictifs)
scripts/gen_keys.sh                  # clés RSA dans secrets/ (jamais commitées)
cd infra && docker compose up -d --build
```

L'`entrypoint.sh` du conteneur applique les migrations (`alembic upgrade head`), lance le
seed si `SEED_DEMO_DATA=true`, puis démarre uvicorn. Le service n'est joignable que via la
gateway : `http://localhost:8080/auth/...` (documentation interactive sur `/auth/docs`).

### En local, sans Docker (développement)

Pré-requis : un PostgreSQL avec le rôle `poupal_auth` et le schéma `auth`
(voir `infra/db/init/01-init.sh`), et une paire de clés RSA.

```bash
cd services/auth
python -m venv .venv && . .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
../../scripts/gen_keys.sh                        # crée secrets/jwt_private.pem et jwt_public.pem

export DATABASE_URL="postgresql+psycopg://poupal_auth:<mot de passe>@localhost:5432/poupal"
export JWT_PRIVATE_KEY_PATH=../../secrets/jwt_private.pem
export JWT_PUBLIC_KEY_PATH=../../secrets/jwt_public.pem

alembic upgrade head                              # crée auth.users et la vue auth.user_directory
DEMO_PASSWORD='<mot de passe de démo>' python -m app.seed   # facultatif
uvicorn app.main:app --port 8001 --reload
```

Un fichier `.env` dans `services/auth/` est lu automatiquement (il est ignoré par Git).

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `DATABASE_URL` | — (obligatoire) | URL SQLAlchemy du rôle `poupal_auth` (`postgresql+psycopg://...`) |
| `JWT_PRIVATE_KEY_PATH` | `/run/secrets/jwt_private.pem` | Clé privée RSA (signature des jetons) |
| `JWT_PUBLIC_KEY_PATH` | `/run/secrets/jwt_public.pem` | Clé publique RSA (vérification pour `/auth/me`) |
| `JWT_ISSUER` | `poupal-auth` | Claim `iss` émis et exigé |
| `JWT_EXPIRES_MINUTES` | `30` | Durée de vie des jetons (`expires_in` = 1800 s) |
| `LOGIN_RATE_LIMIT` | `5/60` | Tentatives de connexion autorisées par IP et par fenêtre (secondes) |
| `PASSWORD_MIN_LENGTH` | `10` | Longueur minimale d'un mot de passe à l'inscription |
| `CORS_ORIGINS` | `http://localhost:8080` | Origines autorisées, séparées par des virgules |
| `SEED_DEMO_DATA` | `false` | `true` : `entrypoint.sh` lance `python -m app.seed` au démarrage |
| `DEMO_PASSWORD` | — | Mot de passe commun des 6 comptes de démo (requis par le seed) |
| `SERVICE_NAME` / `LOG_LEVEL` | `poupal-auth` / `INFO` | Nom dans les logs et métriques, niveau de log |

Aucun secret n'est dans le code : les mots de passe de base et de démo viennent de
`infra/.env` (ignoré par Git), les clés JWT sont montées en lecture seule dans `/run/secrets`.

## Endpoints

Format d'erreur unique : `{"message": "...", "code": "..."}` (+ `errors[]` pour un 422).

### `POST /auth/register` → 201

```json
{ "name": "Alex Martin", "email": "alex@poupal.demo", "password": "au-moins-10-caractères" }
```
Réponse : `{ "id", "email", "name", "created_at" }`. L'email est stocké en minuscules.
Erreurs : `409 email_already_used`, `422 validation_error`.

### `POST /auth/login` → 200

```json
{ "email": "alex@poupal.demo", "password": "..." }
```
Réponse : `{ "access_token": "<JWT>", "token_type": "bearer", "expires_in": 1800 }`.
Erreurs : `401 invalid_credentials` (même message pour un email inconnu et un mauvais mot
de passe, avec vérification Argon2 factice à temps constant), `429 rate_limited` + en-tête
`Retry-After` au-delà de `LOGIN_RATE_LIMIT` par IP client.

### `GET /auth/me` → 200 (en-tête `Authorization: Bearer <JWT>`)

Réponse : `{ "id", "email", "name", "created_at" }`.
Erreur : `401 invalid_token` (jeton absent, invalide ou expiré) + `WWW-Authenticate: Bearer`.

### Jeton JWT

RS256, claims `sub` (id utilisateur), `email`, `name`, `iat`, `exp`, `iss`. Vérification
(ici et dans l'API) : `jwt.decode(token, clé_publique, algorithms=["RS256"], issuer=JWT_ISSUER, options={"require": ["exp", "iat", "sub"]})`.

### Techniques

`GET /health` (liveness, toujours 200), `GET /ready` (200 si base joignable **et** clés
chargées, sinon 503 — utilisé par le HEALTHCHECK Docker), `GET /metrics` (Prometheus).
Ces trois routes ne sont pas exposées par la gateway.

## Observabilité

- **Logs JSON** sur stdout (collectés par Loki) : `timestamp, level, service, request_id, user_id`
  + champs de l'événement. Événements métier émis : `user_registered`, `login_success`,
  `login_failed` (`reason` = `unknown_user` | `bad_password`), `login_rate_limited`,
  `token_rejected`, `seed_users`. Le mot de passe, le jeton et l'en-tête `Authorization`
  ne sont **jamais** journalisés (clés filtrées en plus par `core/logging.py`).
- **X-Request-ID** : propagé depuis la gateway ou généré, renvoyé dans chaque réponse.
- **Métriques** : `http_requests_total{service,method,route,status}`,
  `http_request_duration_seconds`, `poupal_db_errors_total` et la métrique métier
  `poupal_login_attempts_total{result="success"|"failure"|"rate_limited"}` — une rafale de
  `failure` ou de `rate_limited` est un signal d'attaque par force brute pour la détection.

## Tests

```bash
scripts/run_tests.sh        # pytest dans l'image (cible "test"), base poupal_test
```

Contrôles rapides sans base : `python -m compileall app` puis
`DATABASE_URL=postgresql+psycopg://x:y@127.0.0.1:1/poupal python -c "import app.main"`.

## Données de démonstration

`python -m app.seed` crée (s'ils manquent) les comptes `alex`, `camille`, `lea`, `nathan`,
`julie`, `hugo` `@poupal.demo`, tous avec le mot de passe `DEMO_PASSWORD`. Le script est
idempotent et termine avec le code 1 si `DEMO_PASSWORD` est absent. Les comptes de paiement et
l'historique de transactions sont créés ensuite par le seed de l'API métier.
