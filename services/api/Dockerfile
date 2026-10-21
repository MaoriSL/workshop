# ---------- Étape 1 : dépendances (image slim, sans outils de build dans l'image finale) ----------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Étape "test" : dépendances de test en plus (utilisée par scripts/run_tests.sh) ----------
FROM base AS test
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN chmod +x entrypoint.sh
# Les tests ont besoin d'écrire des fichiers temporaires (clés) : utilisateur non-root dédié
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app
ENTRYPOINT ["./entrypoint.sh"]

# ---------- Étape finale : exécution, utilisateur non-root ----------
FROM base AS runtime
COPY . .
RUN chmod +x entrypoint.sh && useradd --create-home --uid 10001 app && chown -R app:app /app
USER app
EXPOSE 8000
# Sonde Docker : /ready vérifie la base et les clés (503 sinon). Pas de curl dans l'image slim.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3   CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2).status == 200 else 1)" || exit 1
ENTRYPOINT ["./entrypoint.sh"]
