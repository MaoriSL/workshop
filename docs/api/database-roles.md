# Base de données Poupal — un serveur, deux schémas, deux rôles

> **Environnement de démonstration.** Les mots de passe des rôles sont fictifs, définis dans `infra/.env`
> (copie de `infra/.env.example`, jamais commité). Aucune donnée réelle.

## 1. Le problème à résoudre

Le service `auth` détient les mots de passe (hashés Argon2) ; l'API métier détient l'argent. Si l'API est
compromise (injection, bug, exécution de code), l'attaquant ne doit pouvoir **ni lire les hashs, ni modifier un
utilisateur, ni se créer un compte**. Symétriquement, une compromission d'`auth` ne doit pas permettre de
toucher aux soldes.

Deux serveurs PostgreSQL donneraient cette étanchéité au prix d'un conteneur de plus et d'une double
administration. On obtient le même résultat avec **un seul serveur, deux schémas et deux rôles sans privilège
global** : le principe du moindre privilège est appliqué par PostgreSQL lui-même, pas par le code applicatif.

## 2. Ce qui est en place

Tout est créé par `infra/db/init/01-init.sh`, exécuté **une seule fois** par l'image officielle `postgres:16`
au premier démarrage du volume `db-data` (pour le rejouer : `docker compose down -v`). Les tables, la vue
et la séquence viennent ensuite des migrations Alembic de chaque service, exécutées **avec le rôle du service**
au démarrage de son conteneur (`entrypoint.sh` → `alembic upgrade head`).

```
PostgreSQL 16 — conteneur "db", réseau Docker interne uniquement (port 5432 non publié sur l'hôte)
└── base poupal          (+ base poupal_test, identique, réservée à pytest)
    ├── schéma auth      — propriétaire : poupal_auth
    │   ├── users (id, email, name, password_hash, created_at)
    │   ├── user_directory  = VUE "SELECT id, email, name FROM auth.users"   ← SELECT accordé à poupal_api
    │   └── alembic_version (migrations du service auth)
    └── schéma payments  — propriétaire : poupal_api
        ├── accounts, transactions, idempotency_keys
        ├── transaction_reference_seq (références PP-2026-000412), type transaction_status
        └── alembic_version (migrations du service api)
```

### 2.1 Les rôles

| Rôle | Utilisé par | Peut | Ne peut PAS |
|---|---|---|---|
| `postgres` (superutilisateur) | le script d'init et l'administration manuelle (`psql`) | tout | n'apparaît dans **aucune** `DATABASE_URL` de service |
| `poupal_auth` | service `auth` (`DATABASE_URL` du conteneur auth) | `LOGIN` ; propriétaire du schéma `auth` : DDL et DML sur ses tables, migrations Alembic | aucun droit sur `payments` (pas même `USAGE`) ; pas de `CREATE` sur `public` ; ni `SUPERUSER`, ni `CREATEDB`, ni `CREATEROLE` |
| `poupal_api` | service `api` (`DATABASE_URL` du conteneur api) | `LOGIN` ; propriétaire du schéma `payments` ; `USAGE` sur `auth` ; `SELECT` sur la **vue** `auth.user_directory` uniquement | aucun droit sur `auth.users` ni sur aucune autre table du schéma `auth` ; pas de `CREATE` sur `public` ; ni `SUPERUSER`, ni `CREATEDB`, ni `CREATEROLE` |

Autres garde-fous du script d'init :

- `REVOKE CREATE ON SCHEMA public FROM PUBLIC` : personne ne crée d'objet hors de son schéma.
- `GRANT CONNECT` explicite des deux rôles sur `poupal` et `poupal_test` (pas sur les autres bases).
- Les tables `alembic_version` sont placées dans le schéma de chaque service (`version_table_schema` dans
  `alembic/env.py`) : un service ne voit même pas l'état des migrations de l'autre.

### 2.2 La vue annuaire `auth.user_directory`

C'est **l'unique pont** entre les deux schémas. Elle est créée par la migration `0001_users` du service auth
(donc avec `poupal_auth` comme propriétaire) :

```sql
CREATE VIEW auth.user_directory AS SELECT id, email, name FROM auth.users;
GRANT SELECT ON auth.user_directory TO poupal_api;
```

Pourquoi ça marche : dans PostgreSQL, une vue s'exécute avec les droits de son **propriétaire** (pas de ceux de
l'appelant, sauf option `security_invoker`). `poupal_api` peut donc lire `id, email, name` **à travers** la vue
tout en étant refusé sur `auth.users`. La vue n'expose ni `password_hash` ni `created_at` : seulement ce qui
sert à trouver un destinataire et à nommer une contrepartie. Côté API, elle est mappée en lecture seule par le
modèle `UserDirectory` (`services/api/app/models.py`).

Si l'on veut demain masquer les emails ou filtrer les comptes désactivés, on modifie la vue côté auth : l'API
ne change pas.

### 2.3 Pas de clé étrangère entre schémas

`payments.accounts.user_id` ne référence **pas** `auth.users` : une contrainte `REFERENCES` exigerait un
privilège sur la table d'auth et coupleraient les deux schémas (impossible de migrer l'un sans l'autre).
L'existence de l'utilisateur est vérifiée au niveau métier via la vue annuaire, et `/internal/consistency`
détecte toute incohérence du grand livre.

### 2.4 Secrets de connexion

- Les mots de passe des rôles sont lus par Compose dans `infra/.env` (`AUTH_DB_PASSWORD`, `API_DB_PASSWORD`)
  et injectés dans `DATABASE_URL` de chaque conteneur : jamais dans le code ni dans Git (`.env` est ignoré).
- Le conteneur `db` ne publie aucun port : seule la base est joignable depuis les conteneurs du réseau
  `backend`.
- Chaque service ouvre un petit pool (`pool_size=5`, `pool_pre_ping=True`) et ne contient que des requêtes ORM
  (jamais de SQL construit par concaténation).

## 3. Ce que l'API ne peut PAS faire, même compromise

Avec le rôle `poupal_api`, un attaquant qui contrôlerait entièrement le code de l'API **ne peut pas** :

- lire `auth.users` — donc aucun hash Argon2 à exfiltrer, aucune attaque hors ligne possible ;
- créer, modifier ou supprimer un utilisateur, ni changer l'email d'un compte pour détourner un virement ;
- modifier la vue annuaire ou s'accorder des droits dessus (il n'en est pas propriétaire) ;
- lire ou altérer `auth.alembic_version` (rejouer ou saboter les migrations d'auth) ;
- créer une table, une fonction ou un trigger dans `auth` ou dans `public` ;
- changer d'identité SQL : `poupal_api` n'est membre d'aucun rôle (`SET ROLE` refusé) ;
- émettre un JWT : couche distincte mais même logique, l'API ne détient que la clé **publique**
  (`services/api/app/core/secrets.py`).

Symétriquement, `poupal_auth` ne peut ni lire ni modifier un solde ou une transaction.

Ce que l'API **peut** faire, évidemment : tout sur `payments`, c'est son métier. La protection des soldes
contre un bug de l'API relève d'autres mécanismes, en base et dans le code : contrainte
`CHECK (balance_cents >= 0)`, contrainte `CHECK (amount_cents > 0)`, transaction SQL unique avec verrouillage
des deux comptes dans un ordre constant (`SELECT ... FOR UPDATE`), clés d'idempotence, et le rapport
`/internal/consistency` qui recalcule le grand livre.

## 4. Le vérifier soi-même avec psql

Pré-requis : la base tourne (`cd infra && docker compose up -d db`). À l'intérieur du conteneur, l'image
officielle autorise les connexions locales (socket Unix) sans mot de passe pour n'importe quel rôle : on peut
donc « se mettre à la place » de chaque rôle avec `psql -U <rôle>`. Depuis un autre conteneur il faudrait
`-h db` et le mot de passe de `infra/.env`.

### 4.1 Inventaire (en superutilisateur)

```bash
cd infra
docker compose exec db psql -U postgres -d poupal -c '\du'           # rôles : poupal_auth et poupal_api sans aucun attribut
docker compose exec db psql -U postgres -d poupal -c '\dn+'          # schémas : auth → poupal_auth, payments → poupal_api
docker compose exec db psql -U postgres -d poupal -c '\dp auth.*'    # droits par objet du schéma auth
docker compose exec db psql -U postgres -d poupal -c '\dp payments.*'
```

Lecture de `\dp auth.*` : la colonne *Access privileges* est vide pour `users` et `alembic_version` (droits du
propriétaire seulement), et vaut `poupal_auth=arwdDxt/poupal_auth` + **`poupal_api=r/poupal_auth`** pour
`user_directory` : `r` = `SELECT`, rien d'autre.

### 4.2 Questions directes à PostgreSQL

```sql
-- docker compose exec db psql -U postgres -d poupal
SELECT has_table_privilege('poupal_api', 'auth.users', 'SELECT');             -- f
SELECT has_table_privilege('poupal_api', 'auth.user_directory', 'SELECT');    -- t
SELECT has_table_privilege('poupal_api', 'auth.user_directory', 'INSERT');    -- f
SELECT has_schema_privilege('poupal_api', 'auth', 'CREATE');                  -- f
SELECT has_schema_privilege('poupal_api', 'public', 'CREATE');                -- f
SELECT has_schema_privilege('poupal_auth', 'payments', 'USAGE');              -- f
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole
  FROM pg_roles WHERE rolname LIKE 'poupal_%';                                -- f | f | f pour les deux
SELECT viewowner FROM pg_views
  WHERE schemaname = 'auth' AND viewname = 'user_directory';                  -- poupal_auth
```

### 4.3 À la place de l'API (`poupal_api`)

```bash
docker compose exec db psql -U poupal_api -d poupal
```

```sql
SELECT id, email, name FROM auth.user_directory LIMIT 3;   -- OK : l'annuaire, et rien d'autre
SELECT password_hash FROM auth.users LIMIT 1;              -- ERROR:  permission denied for table users
INSERT INTO auth.users (email, name, password_hash)
  VALUES ('pirate@poupal.demo', 'Pirate', 'x');            -- ERROR:  permission denied for table users
UPDATE auth.user_directory SET email = 'pirate@poupal.demo';  -- ERROR:  permission denied for view user_directory
SELECT * FROM auth.alembic_version;                        -- ERROR:  permission denied for table alembic_version
CREATE TABLE auth.pirate (id int);                         -- ERROR:  permission denied for schema auth
CREATE TABLE public.pirate (id int);                       -- ERROR:  permission denied for schema public
SET ROLE poupal_auth;                                      -- ERROR:  permission denied to set role "poupal_auth"
SELECT count(*) FROM payments.accounts;                    -- OK : son propre schéma
```

### 4.4 À la place d'auth (`poupal_auth`)

```bash
docker compose exec db psql -U poupal_auth -d poupal -c 'SELECT * FROM payments.accounts LIMIT 1'
# ERROR:  permission denied for schema payments
docker compose exec db psql -U poupal_auth -d poupal -c 'SELECT count(*) FROM auth.users'
# OK : son propre schéma
```

### 4.5 Ce que les tests prouvent aussi

La suite pytest de l'API doit insérer des utilisateurs de test dans `auth.users`. Elle ne peut pas le faire
avec sa propre connexion : elle utilise une seconde URL, `TEST_AUTH_DATABASE_URL` (rôle `poupal_auth`, base
`poupal_test`, voir `infra/docker-compose.test.yml`). Cette contrainte dans les tests est la démonstration
quotidienne que la séparation fonctionne.

## 5. Limites connues et suites possibles

- Les mots de passe des rôles sont en clair dans `infra/.env` sur le poste de démo : le passage à Vault ou SOPS
  se fait dans `app/core/secrets.py` de chaque service (point unique de lecture des secrets) et dans la section
  `secrets:` de Compose, sans toucher au reste du code.
- Pas de TLS entre les services et la base (réseau Docker interne) : prévoir `sslmode=require` et des
  certificats pour un déploiement multi-hôtes.
- L'image officielle accepte les connexions locales du conteneur sans mot de passe (`trust` sur le socket) :
  acceptable tant que le conteneur `db` n'est joignable que depuis le réseau interne ; à durcir hors démo
  (`POSTGRES_HOST_AUTH_METHOD`, `pg_hba.conf`).
- Journalisation d'audit (`pgaudit`), sauvegardes et restauration (PCA / PRA) : voir `governance/`.
