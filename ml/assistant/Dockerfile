# Assistant RAG Poupal : les documents restent dans le dépôt, le LLM est distant
# sur le PC Windows de démonstration via Ollama.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY ml/assistant/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ml/assistant /app/ml/assistant
COPY docs /app/docs
RUN touch /app/ml/__init__.py \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app

USER app
EXPOSE 8012
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8012/health', timeout=2)"

CMD ["uvicorn", "ml.assistant.app:app", "--host", "0.0.0.0", "--port", "8012", "--no-access-log"]
