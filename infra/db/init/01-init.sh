#!/usr/bin/env bash
# ------------------------------------------------------------------
# Initialisation PostgreSQL (exécuté UNE fois, au premier démarrage du
# conteneur db, par l'image officielle postgres via /docker-entrypoint-initdb.d).
#
# Principe du moindre privilège :
#   - rôle poupal_auth : propriétaire du schéma "auth"   (utilisateurs, mots de passe hashés)
#   - rôle poupal_api  : propriétaire du schéma "payments" (comptes, transactions)
#   - l'API ne voit du schéma auth QUE la vue auth.user_directory
#     (GRANT SELECT posé par la migration du service auth, propriétaire de la vue).
# La base "poupal_test" reçoit la même structure pour les tests pytest.
# ------------------------------------------------------------------
set -euo pipefail

: "${AUTH_DB_PASSWORD:?AUTH_DB_PASSWORD manquant}"
: "${API_DB_PASSWORD:?API_DB_PASSWORD manquant}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    -- Rôles applicatifs (LOGIN, sans droits globaux)
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'poupal_auth') THEN
            CREATE ROLE poupal_auth LOGIN PASSWORD '${AUTH_DB_PASSWORD}';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'poupal_api') THEN
            CREATE ROLE poupal_api LOGIN PASSWORD '${API_DB_PASSWORD}';
        END IF;
    END
    \$\$;

    CREATE DATABASE poupal_test;
SQL

# Même structure (schémas + droits) dans la base principale et la base de test.
for db in "$POSTGRES_DB" poupal_test; do
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-SQL
    -- Personne ne crée d'objets dans "public" par défaut
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;

    -- Schéma auth : propriété du service d'authentification
    CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION poupal_auth;
    -- Schéma payments : propriété de l'API métier
    CREATE SCHEMA IF NOT EXISTS payments AUTHORIZATION poupal_api;

    -- L'API peut "entrer" dans le schéma auth (USAGE) mais n'a aucun droit sur ses tables :
    -- seul SELECT sur la vue auth.user_directory lui sera accordé par la migration auth.
    GRANT USAGE ON SCHEMA auth TO poupal_api;

    -- Les deux rôles peuvent se connecter à cette base
    GRANT CONNECT ON DATABASE "$db" TO poupal_auth, poupal_api;
SQL
done

echo "Initialisation Poupal terminée : rôles poupal_auth / poupal_api, schémas auth / payments, base poupal_test."
