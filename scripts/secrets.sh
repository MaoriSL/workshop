#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Gestion des secrets Poupal avec SOPS + age (plus léger que Vault : pas de service
# à faire tourner, juste des fichiers chiffrés commitables).
#
#   scripts/secrets.sh decrypt   -> security/secrets/poupal.sops.env  =>  infra/.env
#   scripts/secrets.sh encrypt   -> infra/.env (clés=valeurs)         =>  poupal.sops.env
#   scripts/secrets.sh edit      -> éditer les secrets chiffrés en place
#   scripts/secrets.sh genkey    -> générer la clé age (si absente)
#
# Clé PRIVÉE : secrets/age/keys.txt (hors Git). Fichier chiffré : commitable.
# Tout passe par l'image utilitaire poupal/secrets-tools (SOPS + age).
# ---------------------------------------------------------------------------
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="poupal/secrets-tools:0.1.0"
ENC="security/secrets/poupal.sops.env"
KEY="secrets/age/keys.txt"

build_tools() {
  docker image inspect "$IMAGE" >/dev/null 2>&1 || \
    docker build -q -t "$IMAGE" -f security/secrets/Dockerfile.tools security/secrets >/dev/null
}

run() { MSYS_NO_PATHCONV=1 docker run --rm -v "$(cd "$ROOT_DIR" && pwd -W 2>/dev/null || pwd):/workspace" "$IMAGE" -c "cd /workspace && $*"; }

build_tools
case "${1:-}" in
  genkey)
    run 'mkdir -p secrets/age; [ -f '"$KEY"' ] || age-keygen -o '"$KEY"'; echo "clé publique :"; age-keygen -y '"$KEY"
    ;;
  encrypt)
    PUB="$(run 'age-keygen -y '"$KEY" | tr -d '\r')"
    run 'grep -v "^#" infra/.env | grep "=" | grep -v "^[[:space:]]*$" > /tmp/clean.env && sops --config /dev/null --encrypt --age '"$PUB"' --input-type dotenv --output-type dotenv /tmp/clean.env > '"$ENC"
    echo "Chiffré -> $ENC"
    ;;
  decrypt)
    run 'SOPS_AGE_KEY_FILE='"$KEY"' sops --config /dev/null --decrypt --input-type dotenv --output-type dotenv '"$ENC"' > infra/.env'
    echo "Déchiffré -> infra/.env"
    ;;
  edit)
    run 'SOPS_AGE_KEY_FILE='"$KEY"' EDITOR=vi sops '"$ENC"
    ;;
  *)
    echo "Usage: scripts/secrets.sh {genkey|encrypt|decrypt|edit}"; exit 1
    ;;
esac
