"""
Tentative d'exfiltration de données FICTIVES : requêtes anormales cherchant à aspirer en masse
l'annuaire ou l'historique (énumération d'identifiants, pagination abusive).

Effet attendu : pic de lecture inhabituel, tracé et détectable (volume de requêtes GET très
supérieur au trafic normal, pagination au-delà des bornes). Sert à montrer la surveillance.
Confinement : lecture seule sur des données fictives, cadence et durée bornées, arrêt immédiat.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import httpx

from .base import MAX_DURATION_S, ParamField, RunCounters, Scenario, interruptible_sleep, send

DEMO_EMAIL = "alex@poupal.demo"


class ExfiltrationScenario(Scenario):
    def __init__(self) -> None:
        super().__init__(
            id="exfiltration",
            name="Exfiltration de données (énumération)",
            description="Pagination abusive de l'historique et énumération d'identifiants de transactions.",
            incident_type="exfiltration",
            defense="Pagination plafonnée côté API (limit borné) ; pic de lecture tracé dans le SIEM.",
            params=[
                ParamField("rate_per_s", "Requêtes / seconde", "int", default=40, min=1, max=100, step=5),
                ParamField("duration_s", "Durée", "int", default=40, min=5, max=MAX_DURATION_S, step=5, unit="s"),
            ],
        )

    async def run(self, client: httpx.AsyncClient, params: dict, counters: RunCounters, stop: asyncio.Event) -> None:
        token = await self._login(client, counters)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        interval = 1.0 / max(1, int(params["rate_per_s"]))
        offset = 0
        while not stop.is_set():
            # Pagination au-delà du raisonnable + grande taille de page (plafonnée côté API)
            await send(client, counters, "GET", "/api/transactions", headers=headers,
                       params={"limit": 1000, "offset": offset})
            # Énumération d'identifiants inexistants (sonde l'historique d'autrui)
            await send(client, counters, "GET", f"/api/transactions/{uuid.uuid4()}", headers=headers)
            offset += 1000
            await interruptible_sleep(interval, stop)

    async def _login(self, client, counters):
        r = await send(client, counters, "POST", "/auth/login", json={"email": DEMO_EMAIL, "password": os.environ.get("DEMO_PASSWORD", "")})
        return r.json().get("access_token") if r is not None and r.status_code == 200 else None
