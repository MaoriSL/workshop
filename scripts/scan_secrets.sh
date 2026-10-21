#!/usr/bin/env bash
# Contrôle « aucun secret en clair » : lance gitleaks (conteneur) sur le dépôt.
# À utiliser en pre-commit et avant de produire l'archive de rendu.
#   scripts/scan_secrets.sh
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MSYS_NO_PATHCONV=1 docker run --rm -v "$(cd "$ROOT_DIR" && pwd -W 2>/dev/null || pwd):/repo" \
  zricethezav/gitleaks:v8.21.2 detect --source=/repo --config=/repo/.gitleaks.toml --redact --no-git -v
