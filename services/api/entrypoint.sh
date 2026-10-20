#!/bin/sh
# Démarrage du service api : migrations → seed (optionnel) → serveur.
# Toute commande passée au conteneur (ex. "pytest") remplace le serveur.
set -e

echo "[api] application des migrations (alembic upgrade head)"
alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "[api] insertion des données de démonstration"
  python -m app.seed
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# --proxy-headers : l'IP réelle du client vient de la gateway (X-Forwarded-For)
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-access-log
