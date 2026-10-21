#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Lance un playbook de remédiation Poupal dans le conteneur ansible-runner
# (Linux, WSL2 ou Git Bash). Équivalent de :
#   docker compose -f infra/docker-compose.yml run --rm ansible-runner ansible-playbook playbooks/<p>.yml [options]
# Démarre le proxy filtrant du socket Docker si besoin et construit l'image de
# l'exécuteur si elle n'existe pas encore.
#
# Usage : infra/ansible/run.sh <playbook> [options ansible-playbook...]
#   infra/ansible/run.sh verify
#   infra/ansible/run.sh restart_service -e service=api
#   infra/ansible/run.sh block_ip -e ip=203.0.113.42
# ---------------------------------------------------------------------------
set -euo pipefail

PLAYBOOKS="deploy, restart_service, recreate_service, rollback, backup_db, restore_db, block_ip, unblock_ip, verify"
if [[ $# -lt 1 ]]; then
  echo "Usage : $0 <playbook> [-e variable=valeur ...]" >&2
  echo "Playbooks : $PLAYBOOKS" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT_DIR/infra/docker-compose.yml")
name="${1%.yml}"            # accepte "verify" ou "verify.yml"
shift

# 1. Le proxy filtrant du socket Docker doit tourner (sinon l'exécuteur ne peut rien faire)
"${COMPOSE[@]}" up -d docker-socket-proxy-ansible

# 2. Image de l'exécuteur : construite une seule fois, réutilisée ensuite
image="$("${COMPOSE[@]}" --profile tools config --images ansible-runner)"
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Image $image absente : construction (une seule fois)..."
  "${COMPOSE[@]}" build ansible-runner
fi

# 3. Exécution du playbook (conteneur jetable, dépôt monté en lecture seule).
#    -T : pas de pseudo-terminal (fonctionne aussi sous Git Bash et en CI).
exec "${COMPOSE[@]}" run --rm -T ansible-runner ansible-playbook "playbooks/$name.yml" "$@"
