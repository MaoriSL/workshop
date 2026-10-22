#!/bin/sh
# ------------------------------------------------------------------
# Rôle SQL dédié à postgres_exporter : LECTURE SEULE des vues de statistiques
# (pg_stat_*), aucun accès aux schémas auth et payments.
# Exécuté une fois, au premier démarrage du conteneur db (après 01-init.sh).
# Base déjà initialisée ? Rejouer ce fichier à la main :
#   docker compose exec -e EXPORTER_DB_PASSWORD=... db sh /docker-entrypoint-initdb.d/02-exporter-role.sh
# ------------------------------------------------------------------
set -eu
: "${EXPORTER_DB_PASSWORD:?EXPORTER_DB_PASSWORD manquant}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'poupal_exporter') THEN
            CREATE ROLE poupal_exporter LOGIN PASSWORD '${EXPORTER_DB_PASSWORD}';
        END IF;
    END
    \$\$;
    -- pg_monitor : lecture des vues de supervision (pg_stat_activity, pg_stat_database...)
    GRANT pg_monitor TO poupal_exporter;
    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO poupal_exporter;
    -- Aucun droit sur les schémas métier (défense en profondeur : rien à révoquer, rien n'a été accordé)
SQL

echo "Rôle poupal_exporter (lecture seule, pg_monitor) prêt."
