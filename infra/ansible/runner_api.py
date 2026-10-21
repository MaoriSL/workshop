#!/usr/bin/env python3
"""
API minimale d'exécution des playbooks (conteneur ansible-runner, réseau interne).

Seul client : le moteur de remédiation. Il n'envoie JAMAIS de commande : seulement le nom
d'un playbook pris dans une liste blanche et des variables validées (service de la liste
blanche, adresse IP syntaxiquement valide). Un jeton partagé (RUNNER_TOKEN) est exigé en plus
de l'isolement réseau. Chaque exécution est bornée dans le temps. Bibliothèque standard.

    POST /run  {"playbook": "restart_service", "vars": {"service": "api"}, "timeout_s": 30}
      -> {"ok": true, "rc": 0, "duration_s": 7.4, "output_tail": "..."}
    GET  /health -> ok
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PLAYBOOK_DIR = os.environ.get("PLAYBOOK_DIR", "/workspace/infra/ansible/playbooks")
LISTEN_PORT = int(os.environ.get("RUNNER_PORT", "8011"))
TOKEN = os.environ.get("RUNNER_TOKEN", "")
MAX_TIMEOUT_S = 120

# Liste blanche FERMÉE des playbooks exécutables à distance (pas deploy : jamais depuis le moteur)
ALLOWED_PLAYBOOKS = {
    "restart_service", "recreate_service", "rollback", "block_ip", "unblock_ip",
    "backup_db", "restore_db", "terminate_long_queries", "verify",
}
ALLOWED_SERVICES = {"front", "auth", "api", "db", "gateway"}
ALLOWED_VARS = {"service", "ip", "image_tag", "max_seconds"}
SAFE_VALUE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def validate(payload: dict) -> tuple[str, dict[str, str]]:
    """Renvoie (playbook, variables) ou lève ValueError avec un message clair."""
    playbook = str(payload.get("playbook", ""))
    if playbook not in ALLOWED_PLAYBOOKS:
        raise ValueError(f"playbook refusé : {playbook!r}")
    raw_vars = payload.get("vars") or {}
    if not isinstance(raw_vars, dict):
        raise ValueError("vars doit être un objet")
    variables: dict[str, str] = {}
    for key, value in raw_vars.items():
        if key not in ALLOWED_VARS:
            raise ValueError(f"variable refusée : {key!r}")
        value = str(value)
        if key == "service" and value not in ALLOWED_SERVICES:
            raise ValueError(f"service refusé : {value!r}")
        if key == "ip":
            ipaddress.ip_address(value)                 # ValueError si invalide
        if key == "max_seconds" and not value.isdigit():
            raise ValueError("max_seconds doit être un entier")
        if not SAFE_VALUE.match(value):
            raise ValueError(f"valeur refusée pour {key}")
        variables[key] = value
    return playbook, variables


def run_playbook(playbook: str, variables: dict[str, str], timeout_s: float) -> dict:
    cmd = ["ansible-playbook", f"{PLAYBOOK_DIR}/{playbook}.yml"]
    for key, value in variables.items():
        cmd += ["-e", f"{key}={value}"]           # liste d'arguments : jamais de shell
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        rc, output = proc.returncode, (proc.stdout + proc.stderr)
    except subprocess.TimeoutExpired as exc:
        rc, output = 124, f"délai dépassé ({timeout_s:.0f} s)\n" + ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
    duration = round(time.monotonic() - started, 2)
    tail = "\n".join(output.strip().splitlines()[-25:])
    print(json.dumps({"level": "INFO" if rc == 0 else "WARNING", "service": "ansible-runner", "event": "playbook_run",
                      "playbook": playbook, "vars": variables, "rc": rc, "duration_s": duration}), flush=True)
    return {"ok": rc == 0, "rc": rc, "duration_s": duration, "output_tail": tail}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"message": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/run":
            return self._send(404, {"message": "not found"})
        if TOKEN and self.headers.get("X-Runner-Token", "") != TOKEN:
            return self._send(401, {"message": "jeton invalide"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            playbook, variables = validate(payload)
            timeout_s = min(float(payload.get("timeout_s", 30)), MAX_TIMEOUT_S)
        except (ValueError, json.JSONDecodeError) as exc:
            return self._send(400, {"message": str(exc)})
        self._send(200, run_playbook(playbook, variables, timeout_s))

    def log_message(self, *_args) -> None:
        return


if __name__ == "__main__":
    print(json.dumps({"level": "INFO", "service": "ansible-runner", "event": "runner_api_started", "port": LISTEN_PORT, "playbooks": sorted(ALLOWED_PLAYBOOKS)}), flush=True)
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
    sys.exit(0)
