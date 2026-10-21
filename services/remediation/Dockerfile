# Moteur de remédiation (contexte de build : racine du dépôt, pour embarquer scripts/smoke_test.py).
# Non-root, aucun accès à Docker : il ne parle qu'au runner Ansible (liste blanche de playbooks).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/remediation/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/remediation/app /app/app
COPY scripts/smoke_test.py /app/scripts/smoke_test.py
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app
EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=2).status == 200 else 1)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
