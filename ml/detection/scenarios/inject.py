#!/usr/bin/env python3
"""
Injection de pannes CONTRÔLÉES sur la plateforme Poupal du PC Hôte, pour créer des
anomalies ÉTIQUETÉES (évaluation du détecteur). Chaque scénario :
  1. note son début ;
  2. perturbe la plateforme pendant --duration secondes ;
  3. remet tout en ordre, même en cas d'interruption (Ctrl+C), puis écrit la ligne
     start, end, type, description dans ml/data/labels.csv.

Scénarios (type dans labels.csv) :
  outage      service gelé (docker pause, défaut) ou arrêté (--mode stop) : api ou auth
  overload    pic de charge : générateurs de trafic supplémentaires à forte intensité
  bruteforce  rafale d'échecs de connexion (générateur en mode TRAFFIC_MODE=bruteforce)
  db_slow     base ralentie : une transaction pose un verrou exclusif sur payments.accounts
  label       ajoute à la main une période (ex. attaque réelle lancée depuis le PC Attaquant)

UNIQUEMENT sur notre propre plateforme (projet compose "poupal", machine locale).
Usage : python ml/detection/scenarios/inject.py outage --service api --duration 90
        python ml/detection/scenarios/inject.py db_slow --duration 60
        python ml/detection/scenarios/inject.py label --type attack --start 2026-10-22T14:00:00Z --end 2026-10-22T14:03:00Z
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "ml" / "data" / "labels.csv"
COMPOSE = ["docker", "compose", "-f", str(ROOT / "infra" / "docker-compose.yml")]
PROJECT = "poupal"
PG_USER = os.environ.get("POSTGRES_USER", "postgres")
PG_DB = os.environ.get("POSTGRES_DB", "poupal")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def append_label(start: str, end: str, kind: str, description: str) -> None:
    new_file = not LABELS.exists()
    with LABELS.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["start", "end", "type", "description"])
        writer.writerow([start, end, kind, description])
    print(f"  label : {kind} {start} -> {end} ({description})")


class Scenario:
    """Squelette commun : start() perturbe, stop() rétablit ; durée et étiquetage sont gérés ici."""

    kind = "unknown"

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    def description(self) -> str:
        return self.kind

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def execute(self) -> int:
        start = now_iso()
        print(f"[{self.kind}] début {start}, durée {self.args.duration}s : {self.description()}")
        interrupted = False
        try:
            self.start()
            time.sleep(self.args.duration)
        except KeyboardInterrupt:
            interrupted = True
            print("  interruption : retour à la normale...")
        finally:
            self.stop()
            end = now_iso()
            append_label(start, end, self.kind, self.description() + (" (interrompu)" if interrupted else ""))
            print(f"[{self.kind}] fin {end} : plateforme rétablie")
        return 0


class Outage(Scenario):
    kind = "outage"

    def description(self) -> str:
        return f"{self.args.mode} de {self.args.service}"

    def container(self) -> str:
        return f"{PROJECT}-{self.args.service}"

    def start(self) -> None:
        run(["docker", "pause" if self.args.mode == "pause" else "stop", self.container()])

    def stop(self) -> None:
        run(["docker", "unpause" if self.args.mode == "pause" else "start", self.container()], check=False)
        for _ in range(60):  # attend que le conteneur redevienne healthy
            state = run(["docker", "inspect", "-f", "{{.State.Health.Status}}", self.container()], check=False).stdout.strip()
            if state == "healthy":
                return
            time.sleep(2)


class TrafficBurst(Scenario):
    """Générateurs de trafic supplémentaires, détruits à la fin (docker compose run --rm)."""

    kind = "overload"
    extra_env: dict[str, str] = {"TRAFFIC_INTENSITY": "5.0", "TRAFFIC_USERS": "10"}

    def description(self) -> str:
        return f"{self.args.replicas} générateur(s) supplémentaire(s), {self.extra_env}"

    def start(self) -> None:
        self.names = [f"{PROJECT}-{self.kind}-{i}" for i in range(1, self.args.replicas + 1)]
        for name in self.names:
            cmd = COMPOSE + ["run", "-d", "--rm", "--no-deps", "--name", name]
            for key, value in self.extra_env.items():
                cmd += ["-e", f"{key}={value}"]
            run(cmd + ["traffic-gen"])

    def stop(self) -> None:
        for name in getattr(self, "names", []):
            run(["docker", "rm", "-f", name], check=False)


class BruteForce(TrafficBurst):
    """Même mécanique, mais le générateur enchaîne les mauvais mots de passe."""

    kind = "bruteforce"
    extra_env = {"TRAFFIC_MODE": "bruteforce", "TRAFFIC_INTENSITY": "3.0", "TRAFFIC_USERS": "10"}


class DbSlow(Scenario):
    """Un verrou exclusif sur payments.accounts bloque tous les virements (latence, puis 503)."""

    kind = "db_slow"

    def description(self) -> str:
        return "verrou exclusif sur payments.accounts et payments.transactions"

    def psql(self, sql: str) -> list[str]:
        return ["docker", "exec", f"{PROJECT}-db", "psql", "-U", PG_USER, "-d", PG_DB, "-c", sql]

    def start(self) -> None:
        # Verrou exclusif sur les comptes ET l'historique : lectures et virements bloquent, les requêtes s'accumulent
        sql = f"BEGIN; LOCK TABLE payments.accounts, payments.transactions IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep({self.args.duration + 5}); COMMIT;"
        self.process = subprocess.Popen(self.psql(sql), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        process = getattr(self, "process", None)
        if process and process.poll() is None:
            process.terminate()
        # Termine la session SQL si elle survit : le verrou tombe avec elle
        run(self.psql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query ILIKE '%pg_sleep%' AND pid <> pg_backend_pid();"), check=False)


SCENARIOS = {"outage": Outage, "overload": TrafficBurst, "bruteforce": BruteForce, "db_slow": DbSlow}


def main() -> int:
    parser = argparse.ArgumentParser(description="Injection de pannes contrôlées (plateforme Poupal locale uniquement).")
    sub = parser.add_subparsers(dest="scenario", required=True)
    for name, cls in SCENARIOS.items():
        p = sub.add_parser(name, help=(cls.__doc__ or name).strip())
        p.add_argument("--duration", type=int, default=90, help="durée en secondes (défaut 90)")
        if name == "outage":
            p.add_argument("--service", choices=["api", "auth"], default="api")
            p.add_argument("--mode", choices=["pause", "stop"], default="pause")
        if name in ("overload", "bruteforce"):
            p.add_argument("--replicas", type=int, default=3 if name == "overload" else 1)
    label = sub.add_parser("label", help="ajoute manuellement une période (ex. attaque réelle)")
    label.add_argument("--type", required=True)
    label.add_argument("--start", required=True)
    label.add_argument("--end", required=True)
    label.add_argument("--description", default="")
    args = parser.parse_args()

    if args.scenario == "label":
        append_label(args.start, args.end, args.type, args.description)
        return 0
    return SCENARIOS[args.scenario](args).execute()


if __name__ == "__main__":
    sys.exit(main())
