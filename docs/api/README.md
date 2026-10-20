# docs/api — Documentation d'API Poupal

> Environnement de démonstration : plateforme de paiement fictive, aucune donnée ni paiement réels.

## Contenu

| Fichier | Rôle | Lecteurs |
|---|---|---|
| [`contract.md`](contract.md) | Contrat complet des deux services (auth, api, endpoints techniques, `/internal/consistency`) : exemples de requêtes et réponses, codes d'erreur, et **correspondance fonction par fonction avec `frontend/poupal/src/api/`** | front, remédiation, supervision, jury |
| [`database-roles.md`](database-roles.md) | Choix de sécurité de la base : un serveur, deux schémas, deux rôles, vue annuaire, ce que l'API ne peut pas faire, et comment le vérifier avec `psql` | cyber, infra, jury |
| `auth-openapi.json` | Spécification OpenAPI du service auth, **générée** depuis le code FastAPI | outillage (Swagger, Postman, génération de clients) |
| `api-openapi.json` | Spécification OpenAPI de l'API métier, **générée** depuis le code FastAPI | idem |

Les deux fichiers OpenAPI sont des artefacts générés : ne pas les éditer à la main. Le contrat lisible
(`contract.md`) reste la référence pour les règles métier (ordre d'évaluation, idempotence, messages).

À lire aussi : `services/auth/README.md`, `services/api/README.md` (lancement et interfaces de chaque
service), `infra/.env.example` (variables) et `scripts/smoke_test.py` (parcours de bout en bout).

## Consulter la documentation interactive

Quand la plateforme tourne (`cd infra && docker compose up -d`), FastAPI sert Swagger UI à travers la gateway :

- auth : <http://localhost:8080/auth/docs> (JSON : `/auth/openapi.json`)
- api : <http://localhost:8080/api/docs> (JSON : `/api/openapi.json`)

Les endpoints `/health`, `/ready`, `/metrics` et `/internal/consistency` n'y sont pas exposés : la gateway ne
les route pas (voir `contract.md`, sections 5 et 6).

## Régénérer les fichiers OpenAPI

À refaire après tout changement de `app/schemas.py` ou d'un routeur, puis commiter (`docs: régénère les
OpenAPI`). Le script `scripts/export_openapi.py` importe les deux applications FastAPI **sans se connecter à
rien** : il place dans l'environnement une `DATABASE_URL` factice et des chemins de clés factices, puis écrit
`docs/api/auth-openapi.json` et `docs/api/api-openapi.json`.

```bash
# Depuis la racine du dépôt, avec un venv contenant les dépendances des services
# (requirements.txt est identique pour auth et api).
python -m venv .venv
. .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -r services/api/requirements.txt
python scripts/export_openapi.py
```

Alternative sans venv, quand la plateforme tourne (même résultat, produit par les conteneurs) :

```bash
curl -s http://localhost:8080/auth/openapi.json | python -m json.tool > docs/api/auth-openapi.json
curl -s http://localhost:8080/api/openapi.json  | python -m json.tool > docs/api/api-openapi.json
```

Vérification rapide qu'un fichier est à jour : comparer le `diff` entre la sortie du script et le fichier
commité ; une différence signifie qu'un schéma ou une route a changé sans régénération.
