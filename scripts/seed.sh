#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Poupal — (re)lance l'insertion des données de démonstration dans les
# conteneurs EN COURS D'EXÉCUTION (après « cd infra && docker compose up -d »).
#
# Ordre imposé : auth d'abord (utilisateurs), api ensuite (comptes + transactions,
# qui lit les utilisateurs dans la vue auth.user_directory).
# Idempotent : auth ne recrée pas un utilisateur existant, api ne fait rien si
# des transactions existent déjà. Le mot de passe commun des comptes de démo
# vient de DEMO_PASSWORD (infra/.env), jamais du code.
#
# Au démarrage normal, entrypoint.sh fait déjà ce seed si SEED_DEMO_DATA=true :
# ce script sert quand la plateforme a été lancée sans, ou après un reset.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Le dossier du premier fichier -f (infra/) sert de projet : infra/.env y est lu.
COMPOSE=(docker compose -f infra/docker-compose.yml)

# -T : pas de pseudo-terminal (fonctionne aussi en CI et sous Git Bash).
# set -e : l'api n'est seedée que si le seed auth a réussi.
echo "==> [auth] utilisateurs de démonstration (python -m app.seed)"
"${COMPOSE[@]}" exec -T auth python -m app.seed

echo "==> [api] comptes et transactions de démonstration (python -m app.seed)"
"${COMPOSE[@]}" exec -T api python -m app.seed

echo "Seed terminé."
