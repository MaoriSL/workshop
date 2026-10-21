# secrets/

Ce dossier contient les clés JWT **générées localement** par `scripts/gen_keys.sh` :

- `jwt_private.pem` : clé privée RSA 2048 — utilisée **uniquement** par le service `auth` pour signer les jetons.
- `jwt_public.pem`  : clé publique — montée dans `auth` et `api` pour vérifier les jetons.

Tout le dossier est ignoré par Git (voir `.gitignore` à la racine), sauf ce fichier.
Les clés sont montées **en lecture seule** dans les conteneurs (`/run/secrets/`).
Le passage à Vault / SOPS remplacera la lecture de ces fichiers dans `app/core/secrets.py`
de chaque service, sans toucher au reste du code.
