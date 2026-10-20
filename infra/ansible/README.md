# infra/ansible — remédiation automatisée (Ansible)

Playbooks Ansible qui **réparent la plateforme Poupal sans intervention humaine** :
redémarrer ou recréer un service, revenir à la version précédente, sauvegarder /
restaurer la base, bloquer une IP à la gateway, et surtout **prouver** que la
plateforme fonctionne de nouveau (smoke test = une vraie transaction qui réussit).

Ils sont appelés par le moteur de remédiation (`services/remediation`) à la détection
d'une anomalie, et peuvent aussi être lancés à la main (démo, exercice PCA/PRA).
Environnement de démonstration : plateforme fictive, aucune donnée réelle.

## Comment ça tourne : un conteneur, un proxy du socket Docker

Les playbooks s'exécutent dans un conteneur jetable (`ansible-runner`, image
`poupal/ansible-runner`, utilisateur non-root, dépôt monté **en lecture seule** sur
`/workspace`). Ce conteneur ne voit jamais le socket Docker complet : il parle à
`docker-socket-proxy-ansible`, un proxy qui n'autorise **que** les appels nécessaires
(lister / inspecter, démarrer / arrêter / redémarrer, créer / supprimer, exec, images,
réseaux, volumes) et refuse le reste (`build`, `commit`, `swarm`, `system`, `plugins`…).

Pourquoi ? L'outil de réparation est, par construction, puissant. Si un attaquant en
prenait le contrôle (playbook modifié, conteneur compromis), le proxy borne les dégâts :
pas d'image reconstruite avec du code malveillant, pas d'accès au démon lui-même, pas de
conteneur privilégié lancé hors du projet. Le proxy des logs (`docker-socket-proxy-logs`,
utilisé par Alloy) est encore plus restreint : lecture seule.

```
ansible-runner ──DOCKER_HOST──▶ docker-socket-proxy-ansible ──/var/run/docker.sock──▶ démon Docker
 (playbooks,                    (liste blanche d'appels API)
  compose, smoke test)
```

## Pré-requis

- `infra/.env` renseigné (copie de `.env.example`) et clés JWT dans `secrets/`
  (`scripts/gen_keys.sh`) : compose les monte dans les conteneurs recréés.
- Images **déjà construites** : `cd infra && docker compose up -d --build` une première
  fois. Les playbooks ne construisent ni ne téléchargent jamais d'image
  (`build: never`, `pull: never`) : on redéploie ce qui a été validé, rien d'autre.
- Image de l'exécuteur : `docker compose build ansible-runner` (les lanceurs le font
  automatiquement si elle manque).

## Utilisation

```powershell
# Windows (PowerShell)
infra\ansible\run.ps1 verify
infra\ansible\run.ps1 restart_service -e service=api
```

```bash
# Linux / WSL2 / Git Bash
infra/ansible/run.sh verify
infra/ansible/run.sh block_ip -e ip=203.0.113.42
```

Les lanceurs démarrent le proxy si besoin puis exécutent l'équivalent de :

```bash
docker compose -f infra/docker-compose.yml run --rm ansible-runner ansible-playbook playbooks/<playbook>.yml -e service=api
```

Code de retour : `0` si l'action a réussi, non nul sinon (exploitable par le moteur de
remédiation et par les scripts).

| Playbook               | Variables                                   | Ce qu'il fait                                                                                                                         |
|------------------------|---------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `verify.yml`           | —                                           | Smoke test de bout en bout (login → virement 1,00 € → solde) + `/internal/consistency`. Affiche `VERIFY OK` / `VERIFY KO`.           |
| `restart_service.yml`  | `service`                                   | `docker compose restart` du service, attente « healthy ».                                                                             |
| `recreate_service.yml` | `service`                                   | Détruit et recrée le conteneur depuis son image d'origine (`--force-recreate --no-deps`), volumes de données conservés, attente « healthy ». |
| `rollback.yml`         | `service` (auth, api, front), `image_tag` (défaut `previous`) | Recrée le service avec `poupal/<service>:<image_tag>`. Échoue proprement si l'image n'existe pas.                      |
| `deploy.yml`           | —                                           | Garde l'image en service sous le tag `previous`, `docker compose up` de toute la plateforme, attente « healthy », smoke test.         |
| `backup_db.yml`        | `keep_backups` (défaut 10)                  | `pg_dump -Fc` dans le volume `db-backups` (`/backups`), validation `pg_restore --list`, rotation.                                     |
| `restore_db.yml`       | `backup_file` (défaut : la plus récente valide) | `pg_restore --clean --if-exists`, puis contrôle de cohérence du ledger (échec si `status ≠ ok`).                                   |
| `block_ip.yml`         | `ip` (IPv4 / IPv6, CIDR accepté)            | Ajoute `deny <ip>;` à la liste de blocage de la gateway, `nginx -t && nginx -s reload` (sans coupure), vérifie que la gateway répond. |
| `unblock_ip.yml`       | `ip`                                        | Retire la règle et recharge nginx. Idempotent, comme `block_ip.yml`.                                                                  |

Services acceptés par `service` : tous ceux du `docker-compose.yml` (`db`, `auth`, `api`,
`front`, `gateway`, `prometheus`, `grafana`, `loki`, `alloy`, exporters, `traffic-gen`…),
**sauf** les deux proxys du socket Docker et l'exécuteur lui-même (`excluded_services`
dans `inventory/hosts.yml`) : l'exécuteur passe par les proxys pour agir, les arrêter
couperait sa propre connexion.

## Redémarrer, recréer ou restaurer ?

- **Redémarrer** (`restart_service`) : le même conteneur repart. Suffit quand un
  processus est bloqué ou saturé (fuite mémoire, boucle). Rapide, rien n'est perdu.
- **Recréer** (`recreate_service`) : le conteneur est détruit et reconstruit à partir de
  son **image d'origine** (immutable). C'est la réponse à un conteneur potentiellement
  compromis : fichiers modifiés, binaire injecté, configuration altérée disparaissent.
  Les volumes nommés (données PostgreSQL, sauvegardes, liste de blocage) ne sont pas
  touchés.
- **Revenir en arrière** (`rollback`) : même mécanisme, mais avec l'image taguée
  `previous` par le dernier `deploy.yml` — utile si la version fraîchement déployée est
  elle-même le problème. Pour rendre le retour définitif, reporter le tag dans
  `infra/.env` (`API_IMAGE_TAG=…`), sinon le prochain `docker compose up` reviendra au tag
  du `.env`.
- **Restaurer** (`restore_db`) : quand les **données** sont atteintes (corruption,
  altération), on repart de la dernière sauvegarde valide puis on vérifie que le ledger
  est cohérent. Les propriétaires des objets (`poupal_auth`, `poupal_api`) sont conservés
  afin que les rôles à privilèges minimaux gardent leurs droits.

Dans tous les cas, la preuve de reprise est **une nouvelle transaction qui réussit**
(`verify.yml`, ou le smoke test intégré à `deploy.yml`), pas seulement un conteneur
qui redémarre.

## Journalisation : chaque action laisse une trace

Chaque playbook se termine (succès **ou** échec, via `block` / `rescue` / `always`) par
`_log_action.yml`, qui émet une ligne JSON sur la sortie standard et la pousse dans Loki :

```json
{"timestamp": "2026-10-20T08:08:02Z", "level": "info", "service": "remediation",
 "event": "remediation_action", "action": "restart_service", "service_target": "api",
 "result": "ok", "duration_s": 23.36, "details": "api redémarré et healthy"}
```

Labels Loki : `service=remediation`, `level` (`info` / `error`), `event=remediation_action`.
Dans Grafana : tableau de bord « Poupal — Logs », panneau « Actions de remédiation »
(requête `{service="remediation"} | json`). Loki injoignable ne fait jamais échouer le
playbook : l'action compte plus que sa trace.

## Fonctionnement interne (pour relire le code)

- `inventory/hosts.yml` : `localhost`, connexion locale ; variables communes (projet,
  chemins, services autorisés, bornes d'attente : 60 × 2 s).
- `playbooks/_compose_project.yml` : compose s'exécute **dans** le conteneur, mais c'est
  le démon Docker, **côté hôte**, qui monte les fichiers (nginx.conf, clés JWT…). Les
  chemins relatifs du `docker-compose.yml` seraient résolus en `/workspace/…`, chemin
  inconnu de l'hôte. Le playbook lit donc, dans les montages du conteneur `ansible-runner`
  lui-même, l'endroit où l'hôte voit le dépôt (source du montage `/workspace`), fait
  résoudre les chemins par `docker compose config --no-interpolate` (variables `${…}`
  conservées : aucun mot de passe n'est écrit dans le fichier temporaire) et remplace le
  préfixe `/workspace` par le chemin de l'hôte dans les clés `source:` / `file:` /
  `context:`. Fonctionne avec un hôte Linux comme avec Docker Desktop sous Windows
  (chemins `C:/…`). Cas non couvert : un dépôt situé dans le système de fichiers d'une
  distribution WSL (chemin de partage opaque) — placer le dépôt sur un disque Windows.
- `playbooks/_wait_healthy.yml` : boucle `docker_container_info` jusqu'à
  `State.Health.Status == healthy` (ou `running` pour un conteneur sans healthcheck),
  60 essais × 2 s au maximum.
- Conséquence du point précédent : compose compare un « hash de configuration » stocké sur
  chaque conteneur. Celui calculé dans le conteneur diffère de celui calculé sur l'hôte
  (chemins absolus différents). `deploy.yml` recrée donc, la première fois, les services
  déjà lancés depuis l'hôte ; et un `docker compose up -d` lancé ensuite depuis l'hôte
  recrée ceux que les playbooks ont recréés. Sans effet sur les données (volumes nommés).
- État persistant de l'exécuteur : volume `ansible-state` monté sur `/var/lib/poupal-ansible`
  (ex. `backups.log`, historique des sauvegardes). Les sauvegardes elles-mêmes vivent dans
  le volume `db-backups` du conteneur `poupal-db`.
- Versions épinglées dans le `Dockerfile` (ansible-core, SDK docker, CLI docker, plugin
  compose) et `requirements.yml` (collection `community.docker`) : image reproductible.

## Tests réalisés (Docker Desktop, Windows, pile complète)

`verify` (VERIFY OK), `restart_service -e service=api`, `recreate_service` (api : clés JWT
remontées ; gateway : nginx.conf remonté, port publié de nouveau joignable),
`block_ip` / `unblock_ip` (`deny 203.0.113.42;` ajouté puis retiré, nginx rechargé sans
coupure, IP invalide refusée), `backup_db` (archive validée, rotation),
`restore_db` (restauration + cohérence `ok`), `rollback` (vers `previous` puis retour ;
image absente → échec propre), `deploy` (tags `previous` posés, 7 services recréés par
compose, 14 services healthy, smoke test OK), lanceurs `run.ps1` et `run.sh`.
