# Secrets (SOPS + age)

- `poupal.sops.env` : secrets de la plateforme, **chiffrés** (AES-256-GCM, clé age). Commitable.
- La clé **privée** est dans `secrets/age/keys.txt` à la racine (hors Git).
- Déchiffrer avant de déployer : `scripts/secrets.sh decrypt` → écrit `infra/.env` (gitignored).
- Modifier : `scripts/secrets.sh edit` (ou éditer `infra/.env` puis `scripts/secrets.sh encrypt`).
- `Dockerfile.tools` : image utilitaire (SOPS + age), construite à la demande par `scripts/secrets.sh`.

Pourquoi SOPS et pas Vault : SOPS chiffre des fichiers (aucun service à faire tourner), adapté au
budget RAM du PC Hôte. Justification complète dans `docs/security.md` §6.
