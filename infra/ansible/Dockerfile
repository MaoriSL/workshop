# ---------------------------------------------------------------------------
# Poupal — image « ansible-runner » : exécute les playbooks de remédiation.
#
# Contenu : ansible-core + collection community.docker, SDK Python docker,
# CLI docker + plugin compose (nécessaires au module docker_compose_v2).
# Aucun démon Docker ici : tout passe par DOCKER_HOST=tcp://docker-socket-proxy-ansible:2375,
# un proxy qui n'autorise qu'une liste précise d'appels (voir README.md).
# Utilisateur non-root ; le dépôt est monté en lecture seule sur /workspace par compose.
#
# Construction : cd infra && docker compose build ansible-runner
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Versions épinglées (image reproductible). La version de Debian est lue dans
# /etc/os-release pour composer le nom exact des paquets Docker
# (ex. docker-ce-cli=5:29.8.2-1~debian.13~trixie).
ARG ANSIBLE_CORE_VERSION=2.21.5
ARG DOCKER_SDK_VERSION=7.2.0
ARG REQUESTS_VERSION=2.34.2
ARG DOCKER_CLI_VERSION=29.8.2
ARG COMPOSE_PLUGIN_VERSION=5.6.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ANSIBLE_COLLECTIONS_PATH=/usr/share/ansible/collections

# 1. CLI docker + plugin compose, depuis le dépôt apt officiel de Docker (clé vérifiée par apt)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc; \
    chmod a+r /etc/apt/keyrings/docker.asc; \
    . /etc/os-release; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        "docker-ce-cli=5:${DOCKER_CLI_VERSION}-1~debian.${VERSION_ID}~${VERSION_CODENAME}" \
        "docker-compose-plugin=${COMPOSE_PLUGIN_VERSION}-1~debian.${VERSION_ID}~${VERSION_CODENAME}"; \
    rm -rf /var/lib/apt/lists/*

# 2. Ansible et bibliothèques Python utilisées par les modules community.docker
RUN pip install --no-cache-dir \
        "ansible-core==${ANSIBLE_CORE_VERSION}" \
        "docker==${DOCKER_SDK_VERSION}" \
        "requests==${REQUESTS_VERSION}"

# 3. Collection community.docker (version épinglée dans requirements.yml)
COPY requirements.yml /tmp/requirements.yml
RUN ansible-galaxy collection install -r /tmp/requirements.yml -p "${ANSIBLE_COLLECTIONS_PATH}" \
    && rm -f /tmp/requirements.yml

# 4. Utilisateur non-root et dossier d'état persistant (volume ansible-state de compose).
#    Le volume hérite des droits de ce dossier lors de sa création.
RUN useradd --create-home --uid 10001 ansible \
    && mkdir -p /var/lib/poupal-ansible \
    && chown ansible:ansible /var/lib/poupal-ansible
USER ansible

# ansible.cfg est lu depuis le dépôt monté : désigné explicitement, car Ansible ignore
# un ansible.cfg trouvé dans un répertoire « world-writable » (cas d'un montage Windows).
ENV ANSIBLE_CONFIG=/workspace/infra/ansible/ansible.cfg
WORKDIR /workspace/infra/ansible

# Par défaut : affiche la version (la commande réelle est passée par « docker compose run »)
CMD ["ansible-playbook", "--version"]
