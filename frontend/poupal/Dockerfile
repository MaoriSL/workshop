# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Poupal — image de production du front (environnement de démonstration,
# plateforme fictive, aucun paiement réel).
#
# Build en deux étapes :
#   1. "build"   : Node compile l'application React/Vite dans dist/
#   2. "runtime" : nginx sert les fichiers statiques (image finale légère)
#
# Exemple :
#   docker build -t poupal-front --build-arg VITE_API_URL=http://localhost:8000/api .
#   docker run --rm -p 8080:80 poupal-front
# ---------------------------------------------------------------------------

# ---- Étape 1 : build -------------------------------------------------------
FROM node:24-alpine AS build
WORKDIR /app

# Les variables VITE_* sont lues par Vite AU MOMENT DU BUILD (pas à l'exécution).
# Vides par défaut = mode mock (données factices embarquées).
ARG VITE_API_URL=
ARG VITE_USE_MOCK=
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_USE_MOCK=$VITE_USE_MOCK

# Dépendances d'abord (couche mise en cache tant que le lockfile ne change pas).
COPY package.json package-lock.json ./
RUN npm ci

# Sources ensuite (.dockerignore exclut node_modules, dist, .env, .git…).
COPY . .
RUN npm run build

# ---- Étape 2 : serveur statique nginx -------------------------------------
FROM nginx:alpine AS runtime

# Configuration nginx : SPA, cache, gzip, /healthz, en-têtes de sécurité.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Fichiers compilés uniquement : aucune source, aucun secret dans l'image finale.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# Sonde de vie : Docker marque le conteneur "unhealthy" si /healthz ne répond plus.
# C'est ce signal qu'exploitent la supervision et la remédiation automatique.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
