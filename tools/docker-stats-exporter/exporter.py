#!/usr/bin/env python3
"""
Exporter Prometheus des conteneurs Poupal (CPU, mémoire, réseau, redémarrages).

Pourquoi pas cAdvisor ? Sous Docker Desktop / WSL2 avec le magasin d'images containerd
(driver "overlayfs"), cAdvisor n'arrive pas à lire les couches des conteneurs
("failed to identify the read-write layer ID") et n'expose aucune métrique par conteneur.
Cet exporter interroge l'API Docker (`/containers/json`, `/containers/{id}/stats`) via le
proxy du socket EN LECTURE SEULE, et publie les MÊMES noms de métriques que cAdvisor,
avec un label `container` = nom du service compose. Les règles Prometheus et les
dashboards restent donc inchangés. Bibliothèque standard uniquement.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DOCKER_URL = os.environ.get("DOCKER_URL", "http://docker-socket-proxy-logs:2375").rstrip("/")
PROJECT = os.environ.get("COMPOSE_PROJECT", "poupal")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9417"))
INTERVAL = float(os.environ.get("SCRAPE_INTERVAL", "5"))
TIMEOUT = float(os.environ.get("DOCKER_TIMEOUT", "4"))

_lock = threading.Lock()
_samples: dict[str, dict] = {}   # service compose -> dernières valeurs
_last_error: str | None = None


def docker_get(path: str) -> dict | list:
    with urllib.request.urlopen(f"{DOCKER_URL}{path}", timeout=TIMEOUT) as response:
        return json.loads(response.read().decode())


def list_project_containers() -> list[dict]:
    """Conteneurs (en cours ou arrêtés) du projet compose, avec leur nom de service."""
    filters = json.dumps({"label": [f"com.docker.compose.project={PROJECT}"]})
    containers = docker_get("/containers/json?all=true&filters=" + urllib.request.quote(filters))
    result = []
    for c in containers:
        service = c.get("Labels", {}).get("com.docker.compose.service")
        if service:
            result.append({"id": c["Id"], "service": service})
    return result


def read_stats(container: dict) -> dict:
    """Une mesure : CPU cumulé (s), mémoire utile (octets), réseau cumulé (octets), redémarrages."""
    inspect = docker_get(f"/containers/{container['id']}/json")
    running = bool(inspect.get("State", {}).get("Running"))
    sample = {"running": running, "restarts": int(inspect.get("RestartCount", 0)),
              "cpu_seconds": 0.0, "memory_bytes": 0, "rx_bytes": 0, "tx_bytes": 0}
    if not running:
        return sample
    stats = docker_get(f"/containers/{container['id']}/stats?stream=false&one-shot=true")
    cpu_ns = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
    sample["cpu_seconds"] = cpu_ns / 1e9                    # nanosecondes -> secondes (cumulé)
    memory = stats.get("memory_stats", {})
    inactive = memory.get("stats", {}).get("inactive_file", 0)
    sample["memory_bytes"] = max(memory.get("usage", 0) - inactive, 0)   # "working set", comme cAdvisor
    for net in (stats.get("networks") or {}).values():
        sample["rx_bytes"] += int(net.get("rx_bytes", 0))
        sample["tx_bytes"] += int(net.get("tx_bytes", 0))
    return sample


def collector_loop() -> None:
    """Rafraîchit les mesures toutes les INTERVAL secondes, en arrière-plan."""
    global _last_error
    while True:
        started = time.monotonic()
        try:
            fresh: dict[str, dict] = {}
            for container in list_project_containers():
                try:
                    fresh[container["service"]] = read_stats(container)
                except (urllib.error.URLError, OSError, ValueError, KeyError):
                    continue   # conteneur disparu entre la liste et la lecture
            with _lock:
                _samples.clear()
                _samples.update(fresh)
            _last_error = None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            _last_error = str(exc)[:200]
            print(json.dumps({"level": "WARNING", "service": "docker-stats-exporter",
                              "event": "docker_unreachable", "error": _last_error}), flush=True)
        time.sleep(max(0.5, INTERVAL - (time.monotonic() - started)))


METRICS = (
    ("container_cpu_usage_seconds_total", "counter", "Temps CPU cumulé du conteneur (secondes).", "cpu_seconds"),
    ("container_memory_working_set_bytes", "gauge", "Mémoire utile du conteneur (octets).", "memory_bytes"),
    ("container_network_receive_bytes_total", "counter", "Octets reçus (cumulé).", "rx_bytes"),
    ("container_network_transmit_bytes_total", "counter", "Octets émis (cumulé).", "tx_bytes"),
    ("container_restart_count", "gauge", "Nombre de redémarrages du conteneur.", "restarts"),
    ("container_running", "gauge", "1 si le conteneur tourne.", "running"),
)


def render() -> str:
    """Format texte Prometheus (mêmes noms de métriques que cAdvisor)."""
    with _lock:
        samples = dict(_samples)
    lines: list[str] = []
    for name, kind, help_text, key in METRICS:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        for service, sample in sorted(samples.items()):
            value = sample[key]
            value = int(value) if isinstance(value, bool) else value
            lines.append(f'{name}{{container="{service}"}} {value}')
    lines.append("# HELP docker_stats_exporter_up 1 si l'API Docker répond.")
    lines.append("# TYPE docker_stats_exporter_up gauge")
    lines.append(f"docker_stats_exporter_up {0 if _last_error else 1}")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (nom imposé par http.server)
        if self.path.startswith("/metrics"):
            status, content_type, body = 200, "text/plain; version=0.0.4; charset=utf-8", render().encode()
        elif self.path.startswith("/health"):
            status, content_type, body = 200, "text/plain", b"ok\n"
        else:
            status, content_type, body = 404, "text/plain", b"not found\n"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:  # pas de log d'accès (bruit inutile)
        return


def main() -> int:
    threading.Thread(target=collector_loop, daemon=True).start()
    print(json.dumps({"level": "INFO", "service": "docker-stats-exporter", "event": "exporter_started",
                      "port": LISTEN_PORT, "docker_url": DOCKER_URL}), flush=True)
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
