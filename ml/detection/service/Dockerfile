# Détecteur d'anomalies temps réel Poupal (contexte de build : racine du dépôt).
# Lecture seule sur Prometheus, aucun accès à Docker, CPU uniquement, ~150 Mo de RAM.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY ml/detection/requirements-service.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Le paquet ml.detection (features, data, model, service) : le MÊME code qu'à l'entraînement
COPY ml/detection/__init__.py ml/detection/features.py ml/detection/data.py ml/detection/model.py ml/detection/threshold.py /app/ml/detection/
COPY ml/detection/service /app/ml/detection/service
RUN touch /app/ml/__init__.py && useradd --create-home --uid 10001 app && chown -R app:app /app
USER app
EXPOSE 8010
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=2).status == 200 else 1)" || exit 1
CMD ["uvicorn", "ml.detection.service.app:app", "--host", "0.0.0.0", "--port", "8010", "--no-access-log"]
