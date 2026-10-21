# Corrélateur SIEM (lecture seule sur Loki). Non-root, image à tag précis.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app /app/app
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app
EXPOSE 8020
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8020/health', timeout=2).status == 200 else 1)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020", "--no-access-log"]
