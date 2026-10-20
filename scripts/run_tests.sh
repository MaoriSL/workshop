#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Poupal — exécute les tests pytest des deux services DANS leurs images Docker
# (cible « test » des Dockerfiles), contre la base poupal_test.
#
# Usage : scripts/run_tests.sh [--down]
#   --down : arrête et supprime les conteneurs du projet « poupal » à la fin (CI).
#            Par défaut, le conteneur db reste disponible pour la plateforme.
#
# Enchaînement :
#   1. build des images auth / api (cible test, code courant) ;
#   2. db   : démarrage et attente du healthcheck ;
#   3. auth : alembic upgrade head sur poupal_test (crée auth.users et la vue
#             auth.user_directory, dont les tests de l'api ont besoin) ;
#   4. auth : pytest -q ;
#   5. api  : pytest -q (l'entrypoint applique d'abord les migrations api).
# Code de retour : 0 si tout passe, 1 sinon (détail dans le résumé final).
# ---------------------------------------------------------------------------
set -uo pipefail   # pas de -e : on agrège les codes de retour nous-mêmes

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Deux fichiers compose : la surcouche test change la cible de build et la base.
COMPOSE=(docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml)

TEARDOWN=false
[[ "${1:-}" == "--down" ]] && TEARDOWN=true

# --- Pré-requis ---------------------------------------------------------------
if [[ ! -f infra/.env ]]; then
  echo "KO  infra/.env absent : copiez infra/.env.example vers infra/.env et renseignez les mots de passe." >&2
  exit 1
fi
# Compose monte les clés JWT même en test (les tests utilisent ensuite leurs propres clés temporaires).
if [[ ! -f secrets/jwt_private.pem || ! -f secrets/jwt_public.pem ]]; then
  echo "--  clés JWT absentes dans secrets/ : génération via scripts/gen_keys.sh"
  bash scripts/gen_keys.sh || { echo "KO  génération des clés impossible (openssl requis)." >&2; exit 1; }
fi

# --- Étapes -------------------------------------------------------------------
R_BUILD="non exécuté"; R_DB="non exécuté"; R_MIG="non exécuté"; R_AUTH="non exécuté"; R_API="non exécuté"

# run_step <variable résultat> <commande...> : exécute, mémorise OK / KO (code n), renvoie le code
run_step() {
  local var="$1"; shift
  echo
  echo "==> $*"
  "$@"
  local rc=$?
  if [[ $rc -eq 0 ]]; then printf -v "$var" "OK"; else printf -v "$var" "KO (code %s)" "$rc"; fi
  return $rc
}

overall=0
# -T : pas de pseudo-terminal (CI, Git Bash) ; --no-deps : ne redémarre pas auth/api/front.
run_step R_BUILD "${COMPOSE[@]}" build auth api || overall=1
if [[ $overall -eq 0 ]]; then
  run_step R_DB "${COMPOSE[@]}" up -d --wait db || overall=1
fi
if [[ $overall -eq 0 ]]; then
  run_step R_MIG "${COMPOSE[@]}" run --rm --no-deps -T auth alembic upgrade head || overall=1
fi
if [[ $overall -eq 0 ]]; then
  # Les deux suites sont indépendantes : on exécute la seconde même si la première échoue.
  run_step R_AUTH "${COMPOSE[@]}" run --rm --no-deps -T auth pytest -q || overall=1
  run_step R_API  "${COMPOSE[@]}" run --rm --no-deps -T api  pytest -q || overall=1
fi

# --- Résumé -------------------------------------------------------------------
echo
echo "================ Résumé des tests Poupal ================"
printf '  %-34s %s\n' "build des images (cible test)"  "$R_BUILD"
printf '  %-34s %s\n' "base de données (poupal-db)"    "$R_DB"
printf '  %-34s %s\n' "migrations auth (poupal_test)"  "$R_MIG"
printf '  %-34s %s\n' "tests auth (pytest)"            "$R_AUTH"
printf '  %-34s %s\n' "tests api (pytest)"             "$R_API"
echo "========================================================="

if [[ $TEARDOWN == true ]]; then
  # Sans -v : le volume de données de la plateforme n'est jamais supprimé ici.
  echo "==> arrêt des conteneurs du projet (--down)"
  "${COMPOSE[@]}" down --remove-orphans
fi

if [[ $overall -eq 0 ]]; then echo "TESTS OK"; else echo "TESTS KO"; fi
exit $overall
