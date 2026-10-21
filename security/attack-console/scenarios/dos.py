"""
Déni de service CONTRÔLÉ : montée en charge HTTP sur l'API via la gateway.

Effet attendu : latence et taux d'erreurs qui montent → le détecteur ML classe « surcharge ».
Défense attendue : limitation de débit par IP (429) sur la gateway, puis blocage + redémarrage.
Confinement : requêtes concurrentes et durée bornées ; arrêt immédiat (événement stop).
"""
from __future__ import annotations

import asyncio
import os

import httpx

from .base import MAX_CONCURRENCY, MAX_DURATION_S, ParamField, RunCounters, Scenario, interruptible_sleep, send

DEMO_EMAIL = "alex@poupal.demo"


class DoSScenario(Scenario):
    def __init__(self) -> None:
        super().__init__(
            id="dos",
            name="Déni de service contrôlé",
            description="Rafale de requêtes concurrentes sur l'API via la gateway : la latence et les erreurs montent.",
            incident_type="surcharge",
            defense="Limitation de débit par IP (429) sur la gateway, puis blocage de l'IP et redémarrage par la remédiation.",
            params=[
                ParamField("concurrency", "Requêtes simultanées", "int", default=20, min=1, max=MAX_CONCURRENCY, step=1),
                ParamField("duration_s", "Durée", "int", default=60, min=5, max=MAX_DURATION_S, step=5, unit="s"),
            ],
        )

    async def run(self, client: httpx.AsyncClient, params: dict, counters: RunCounters, stop: asyncio.Event) -> None:
        token = await self._login(client, counters)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        paths = ["/api/accounts/me", "/api/transactions?limit=50"] if token else ["/", "/auth/docs"]

        async def worker(index: int) -> None:
            i = 0
            while not stop.is_set():
                await send(client, counters, "GET", paths[(index + i) % len(paths)], headers=headers)
                i += 1
                await interruptible_sleep(0.02, stop)   # ~50 req/s/worker au plus

        await asyncio.gather(*[worker(i) for i in range(int(params["concurrency"]))], return_exceptions=True)

    async def _login(self, client: httpx.AsyncClient, counters: RunCounters) -> str | None:
        response = await send(client, counters, "POST", "/auth/login",
                              json={"email": DEMO_EMAIL, "password": os.environ.get("DEMO_PASSWORD", "")})
        if response is not None and response.status_code == 200:
            return response.json().get("access_token")
        return None
