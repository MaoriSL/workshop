# Générateur de trafic « normal » Poupal — environnement de démonstration (plateforme fictive).
# Bibliothèque standard uniquement : pas de requirements.txt, pas de pip install.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY traffic_gen.py ./

# Utilisateur non-root dédié (même uid 10001 que les services auth et api)
RUN useradd --create-home --uid 10001 traffic && chown -R traffic:traffic /app
USER traffic

# Le healthcheck est défini dans infra/docker-compose.yml : il vérifie que la boucle
# principale touche /tmp/traffic-gen.heartbeat (y compris en veille, TRAFFIC_ENABLED=false).
CMD ["python", "-u", "traffic_gen.py"]
