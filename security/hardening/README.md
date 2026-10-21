# Durcissement (hardening)

Le durcissement est appliqué dans `infra/docker-compose.yml` (pas de fichiers à part) et documenté
dans `docs/security.md` §5. Résumé de ce qui est vérifiable :

- **Non-root** : tous nos services applicatifs tournent en uid 10001 (voir les Dockerfiles).
- **`security_opt: no-new-privileges`** sur tous les conteneurs ; **`cap_drop: ALL`** sur les services
  Python (aucune capability nécessaire). Vérifier : `docker inspect <conteneur> --format '{{.HostConfig.SecurityOpt}} {{.HostConfig.CapDrop}}'`.
- **Réseaux segmentés** : `edge` (WAF, front, trafic), `backend` (auth, api, db), `monitoring`
  (supervision), `console` (console d'attaque). La base n'est que sur `backend`. Seul le WAF publie un
  port ; Grafana/Prometheus sur 127.0.0.1. Vérifier : `docker network inspect poupal_backend`.
- **Accès Docker** : jamais le socket complet — proxy en liste blanche pour l'automatisation.
- **Secrets** : chiffrés (SOPS), jamais en clair dans Git (voir §6 et `scripts/scan_secrets.sh`).

Hors périmètre d'un prototype 4 jours (pistes de mise en production) : systèmes de fichiers en lecture
seule généralisés, secrets runtime dynamiques (Vault), scan d'images (Trivy) en CI, mTLS inter-services.
