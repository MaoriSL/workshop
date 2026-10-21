#!/usr/bin/env bash
# Génère la paire de clés RSA utilisée pour signer (auth) et vérifier (api) les JWT.
# Usage : scripts/gen_keys.sh [dossier]   (défaut : secrets/ à la racine du dépôt)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT_DIR/secrets}"
PRIVATE="$OUT_DIR/jwt_private.pem"
PUBLIC="$OUT_DIR/jwt_public.pem"

mkdir -p "$OUT_DIR"

if [[ -f "$PRIVATE" && -f "$PUBLIC" ]]; then
  echo "Clés déjà présentes dans $OUT_DIR — rien à faire (supprimez-les pour les régénérer)."
  exit 0
fi

echo "Génération d'une clé RSA 2048 bits dans $OUT_DIR ..."
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$PRIVATE" 2>/dev/null
openssl pkey -in "$PRIVATE" -pubout -out "$PUBLIC" 2>/dev/null

# Compose monte les secrets locaux en conservant les permissions du fichier source.
# L'auth tourne en uid non-root dans le conteneur : la clé doit donc être lisible
# par cet utilisateur, tout en restant absente de Git via .gitignore.
chmod 644 "$PRIVATE" 2>/dev/null || true
chmod 644 "$PUBLIC" 2>/dev/null || true

echo "OK : $PRIVATE (privée, auth uniquement) et $PUBLIC (publique, auth + api)."
