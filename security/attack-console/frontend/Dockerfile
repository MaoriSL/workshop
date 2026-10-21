# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Poupal — Console d'attaque (laboratoire). Image de production du front.
# Attaques FICTIVES et CONFINÉES contre notre propre plateforme de démonstration.
#
# Build en deux étapes :
#   1. "build"   : Node compile l'application React/Vite dans dist/
#   2. "runtime" : nginx sert les fichiers statiques (image finale légère)
#
# Exemple :
#   docker build -t poupal-attack-console .
#   docker run --rm -p 8090:80 poupal-attack-console   → http://localhost:8090/
# ---------------------------------------------------------------------------

# ---- Étape 1 : build -------------------------------------------------------
FROM node:24-alpine AS build
WORKDIR /app

# Variables VITE_* lues AU MOMENT DU BUILD (pas à l'exécution).
#   VITE_API_BASE : base de l'API de l'orchestrateur (défaut /api, même origine)
#   VITE_USE_MOCK : "true" = scénarios de démonstration embarqués (sans orchestrateur)
ARG VITE_API_BASE=/api
ARG VITE_USE_MOCK=
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_USE_MOCK=$VITE_USE_MOCK

# Dépendances d'abord (couche mise en cache tant que le lockfile ne change pas).
COPY package.json package-lock.json ./
RUN npm ci

# Sources ensuite (.dockerignore exclut node_modules, dist, .env, .git…).
COPY . .
RUN npm run build

# ---- Étape 2 : serveur statique nginx -------------------------------------
FROM nginx:1.27.5-alpine AS runtime

# Configuration nginx : SPA servie à la racine, cache des assets, /healthz.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Fichiers compilés uniquement : aucune source, aucun secret dans l'image finale.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# Sonde de vie : le conteneur est marqué "unhealthy" si /healthz ne répond plus.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
