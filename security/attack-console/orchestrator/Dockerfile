# Orchestrateur de la console d'attaque (PC Attaquant). Non-root, image à tag précis.
# Contexte de build : security/attack-console (embarque orchestrator/ + scenarios/).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY orchestrator/app /app/app
COPY scenarios /app/scenarios
RUN useradd --create-home --uid 10001 app && mkdir -p /labels && chown -R app:app /app /labels
USER app
EXPOSE 8099
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=2).status == 200 else 1)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099", "--no-access-log"]
