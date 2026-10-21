# Exporter de métriques conteneurs (remplace cAdvisor sous Docker Desktop / WSL2).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY exporter.py ./
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 9417
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9417/health', timeout=2).status == 200 else 1)" || exit 1
CMD ["python", "-u", "exporter.py"]
