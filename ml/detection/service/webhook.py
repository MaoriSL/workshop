"""
Envoi des incidents au moteur de remédiation, signés par HMAC-SHA256.

Le secret est partagé via la variable REMEDIATION_HMAC_SECRET. Le corps JSON est signé
tel quel (octets) ; la signature voyage dans l'en-tête X-Poupal-Signature sous la forme
"sha256=<hex>". Le moteur recalcule le HMAC et refuse tout incident non signé ou altéré.
Tant que l'URL n'est pas configurée, l'incident est seulement journalisé.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

import httpx

SIGNATURE_HEADER = "X-Poupal-Signature"
logger = logging.getLogger("poupal.detector.webhook")


def canonical_body(incident: dict) -> bytes:
    """JSON canonique (clés triées, sans espaces) : le même des deux côtés."""
    return json.dumps(incident, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify(body: bytes, secret: str, signature: str | None) -> bool:
    """Côté moteur de remédiation : comparaison en temps constant."""
    if not signature:
        return False
    return hmac.compare_digest(sign(body, secret), signature)


def send_incident(url: str | None, secret: str, incident: dict, retries: int = 3, timeout: float = 5.0) -> bool:
    """POST signé, avec reprise (1 s, 2 s, 4 s). Renvoie True si le moteur a accepté (2xx)."""
    body = canonical_body(incident)
    if not url:
        logger.info("incident_logged_only", extra={"fields": {"event": "incident_logged_only", "incident_id": incident.get("incident_id"), "state": incident.get("state")}})
        return False
    headers = {"Content-Type": "application/json", SIGNATURE_HEADER: sign(body, secret)}
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            response = httpx.post(url, content=body, headers=headers, timeout=timeout)
            if 200 <= response.status_code < 300:
                logger.info("incident_sent", extra={"fields": {"event": "incident_sent", "incident_id": incident.get("incident_id"), "status": response.status_code}})
                return True
            logger.warning("incident_rejected", extra={"fields": {"event": "incident_rejected", "status": response.status_code, "attempt": attempt}})
        except httpx.HTTPError as exc:
            logger.warning("incident_send_failed", extra={"fields": {"event": "incident_send_failed", "attempt": attempt, "error": str(exc)[:160]}})
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    return False
