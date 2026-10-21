#!/bin/sh
# Exécuté par l'image nginx au démarrage (/docker-entrypoint.d/) : crée la liste de
# blocage si le volume est vide, pour que l'include du fichier n'échoue jamais.
set -e
BLOCKLIST_DIR=/etc/nginx/blocklist
BLOCKLIST_FILE="$BLOCKLIST_DIR/blocked_ips.conf"
mkdir -p "$BLOCKLIST_DIR"
if [ ! -f "$BLOCKLIST_FILE" ]; then
  printf '# IP bloquées par la remédiation automatique (une ligne par IP : deny 203.0.113.42;)\n' > "$BLOCKLIST_FILE"
  echo "[gateway] liste de blocage initialisée : $BLOCKLIST_FILE"
fi
