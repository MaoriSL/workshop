"""
Injection applicative : envoi de charges de TEST SQLi / XSS classiques sur les champs et
paramètres de l'API (chaînes connues des catalogues OWASP).

But : démontrer que la défense applicative fonctionne. L'API Poupal utilise déjà des requêtes
paramétrées (ORM) : l'injection échoue côté applicatif, ET le WAF (CRS OWASP) la bloque en amont
(403) et la trace dans le SIEM. On mesure donc le taux de requêtes bloquées.
Effet attendu : pic de 403 WAF, tracé dans Loki. Aucune donnée réelle, aucune persistance.
"""
from __future__ import annotations

import asyncio

import httpx

from .base import MAX_DURATION_S, ParamField, RunCounters, Scenario, interruptible_sleep, send

# Chaînes de test standard (catalogues OWASP) : servent à vérifier que le WAF déclenche.
SQLI = ["' OR '1'='1", "1; DROP TABLE users; --", "' UNION SELECT NULL,NULL--", "admin'--", "1 OR 1=1"]
XSS = ["<script>alert(1)</script>", "\"><img src=x onerror=alert(1)>", "javascript:alert(document.cookie)"]
TRAVERSAL = ["../../../../etc/passwd", "..%2f..%2f..%2fetc%2fpasswd"]


class InjectionScenario(Scenario):
    def __init__(self) -> None:
        super().__init__(
            id="injection",
            name="Injection applicative (SQLi / XSS)",
            description="Charges de test SQLi, XSS et traversée de chemin sur les paramètres et champs de l'API.",
            incident_type="injection",
            defense="WAF (CRS OWASP) qui bloque (403) et journalise ; côté API, requêtes paramétrées déjà en place.",
            params=[
                ParamField("rate_per_s", "Charges / seconde", "int", default=20, min=1, max=100, step=5),
                ParamField("duration_s", "Durée", "int", default=40, min=5, max=MAX_DURATION_S, step=5, unit="s"),
            ],
        )

    async def run(self, client: httpx.AsyncClient, params: dict, counters: RunCounters, stop: asyncio.Event) -> None:
        payloads = SQLI + XSS + TRAVERSAL
        interval = 1.0 / max(1, int(params["rate_per_s"]))
        i = 0
        while not stop.is_set():
            payload = payloads[i % len(payloads)]
            kind = i % 3
            if kind == 0:   # paramètre de requête (GET)
                await send(client, counters, "GET", "/api/transactions", params={"q": payload, "limit": payload})
            elif kind == 1:   # corps JSON (POST login : l'email reçoit la charge)
                await send(client, counters, "POST", "/auth/login", json={"email": payload, "password": payload})
            else:   # chemin / en-tête
                await send(client, counters, "GET", f"/api/transactions/{payload}", headers={"X-Test-Payload": payload})
            i += 1
            await interruptible_sleep(interval, stop)
