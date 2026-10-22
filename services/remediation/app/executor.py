"""
Exécution des actions : UNIQUEMENT des playbooks Ansible existants, appelés par leur nom
(liste blanche) via l'API du conteneur ansible-runner. Jamais de commande shell construite
à partir d'une donnée reçue. Paramètres validés avant envoi : service dans la liste blanche,
IP syntaxiquement valide ET jamais une adresse de notre propre infrastructure.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import time
from dataclasses import dataclass

import httpx

from .policy import SERVICES

logger = logging.getLogger("poupal.remediation.executor")

RUNNER_URL = os.environ.get("RUNNER_URL", "http://ansible-runner:8011").rstrip("/")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100").rstrip("/")
ACTION_TIMEOUT_S = float(os.environ.get("REMEDIATION_ACTION_TIMEOUT_S", "60"))
DRY_RUN = os.environ.get("REMEDIATION_DRY_RUN", "false").strip().lower() in ("1", "true", "yes")

ALLOWED_PLAYBOOKS = {"restart_service", "recreate_service", "rollback", "block_ip", "unblock_ip", "restore_db", "terminate_long_queries", "backup_db"}

# Adresses que l'on refuse de bloquer : notre propre infrastructure (réseaux Docker, boucle locale,
# lien local) + plages supplémentaires via REMEDIATION_PROTECTED_NETWORKS (ex. 192.168.1.0/24).
PROTECTED_NETWORKS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "::1/128", "172.16.0.0/12", "169.254.0.0/16", "fe80::/10", "fc00::/7", "0.0.0.0/8",
)] + [ipaddress.ip_network(n.strip()) for n in os.environ.get("REMEDIATION_PROTECTED_NETWORKS", "").split(",") if n.strip()]


class ActionRefused(ValueError):
    """Paramètre invalide : l'action n'est pas exécutée."""


def validate_service(service: str) -> str:
    if service not in SERVICES:
        raise ActionRefused(f"service hors liste blanche : {service!r}")
    return service


def validate_ip(value: str) -> str:
    """IP réelle et extérieure à notre infrastructure, sinon ActionRefused."""
    try:
        address = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise ActionRefused(f"adresse IP invalide : {value!r}") from exc
    if address.is_multicast or address.is_reserved or address.is_unspecified:
        raise ActionRefused(f"adresse IP non bloquable : {address}")
    for network in PROTECTED_NETWORKS:
        if address in network:
            raise ActionRefused(f"adresse de notre infrastructure, blocage refusé : {address}")
    return str(address)


def most_aggressive_ip(window: str = "2m", timeout: float = 4.0) -> str | None:
    """IP cliente la plus active dans les logs JSON de la gateway (Loki), hors infrastructure."""
    query = f'topk(5, sum by (client_ip) (count_over_time({{service="poupal-gateway"}} | json | __error__="" [{window}])))'
    try:
        response = httpx.get(f"{LOKI_URL}/loki/api/v1/query", params={"query": query}, timeout=timeout)
        response.raise_for_status()
        results = response.json().get("data", {}).get("result", [])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("loki_unavailable", extra={"fields": {"event": "loki_unavailable", "error": str(exc)[:160]}})
        return None
    ranked = sorted(results, key=lambda r: -float(r["value"][1]))
    for entry in ranked:
        candidate = entry.get("metric", {}).get("client_ip", "")
        try:
            return validate_ip(candidate)
        except ActionRefused:
            continue   # IP interne (générateur de trafic, gateway…) : on passe à la suivante
    return None


@dataclass
class ActionResult:
    action: str
    params: dict
    ok: bool
    duration_s: float
    details: str
    skipped: bool = False

    def to_dict(self) -> dict:
        return {"action": self.action, "params": self.params, "ok": self.ok, "duration_s": self.duration_s, "details": self.details, "skipped": self.skipped}


def run_playbook(playbook: str, variables: dict[str, str], timeout_s: float = ACTION_TIMEOUT_S) -> ActionResult:
    """Appelle l'API du runner (liste blanche côté moteur ET côté runner)."""
    if playbook not in ALLOWED_PLAYBOOKS:
        raise ActionRefused(f"playbook hors liste blanche : {playbook!r}")
    if "service" in variables:
        validate_service(variables["service"])
    if "ip" in variables:
        validate_ip(variables["ip"])
    started = time.monotonic()
    if DRY_RUN:
        logger.info("remediation_action", extra={"fields": {"event": "remediation_action", "action": playbook, "params": variables, "result": "dry_run", "duration_s": 0.0}})
        return ActionResult(playbook, variables, True, 0.0, "dry-run : action journalisée, non exécutée")
    try:
        response = httpx.post(f"{RUNNER_URL}/run", json={"playbook": playbook, "vars": variables, "timeout_s": timeout_s},
                              headers={"X-Runner-Token": RUNNER_TOKEN}, timeout=timeout_s + 10)
        payload = response.json() if response.content else {}
        ok = response.status_code == 200 and bool(payload.get("ok"))
        details = payload.get("message") or (payload.get("output_tail", "") or "")[-300:]
    except (httpx.HTTPError, ValueError) as exc:
        ok, details = False, f"runner injoignable : {str(exc)[:160]}"
    duration = round(time.monotonic() - started, 2)
    logger.log(logging.INFO if ok else logging.WARNING, "remediation_action",
               extra={"fields": {"event": "remediation_action", "action": playbook, "params": variables, "result": "ok" if ok else "ko", "duration_s": duration}})
    return ActionResult(playbook, variables, ok, duration, details)


def blocked_ips(timeout: float = 5.0) -> list[str]:
    """Lit la liste effective des IP bloquées par la gateway."""
    try:
        response = httpx.get(f"{RUNNER_URL}/blocklist", headers={"X-Runner-Token": RUNNER_TOKEN}, timeout=timeout)
        response.raise_for_status()
        items = response.json().get("items", [])
        return [str(item) for item in items if isinstance(item, str)]
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError(f"liste de blocage indisponible : {str(exc)[:160]}") from exc


def execute(action: str, params: dict) -> ActionResult:
    """Exécute une étape du plan ('a+b' = plusieurs playbooks ; '@aggressive' = IP lue dans Loki)."""
    resolved = dict(params)
    if resolved.get("ip") == "@aggressive":
        ip = most_aggressive_ip()
        if ip is None:
            return ActionResult(action, {}, False, 0.0, "aucune IP agressive externe dans les logs de la gateway : étape sautée", skipped=True)
        resolved["ip"] = ip
    results: list[ActionResult] = []
    for playbook in action.split("+"):
        variables = {k: str(v) for k, v in resolved.items() if k in {"service", "ip", "image_tag", "max_seconds"}
                     and (k != "ip" or playbook in ("block_ip", "unblock_ip")) and (k != "service" or playbook not in ("block_ip", "unblock_ip", "restore_db", "terminate_long_queries", "backup_db"))}
        if playbook == "terminate_long_queries":
            variables = {"max_seconds": resolved.get("max_seconds", "5")}
        results.append(run_playbook(playbook, variables))
        if not results[-1].ok:
            break
    ok = all(r.ok for r in results)
    return ActionResult(action, resolved, ok, round(sum(r.duration_s for r in results), 2), " ; ".join(r.details for r in results))
