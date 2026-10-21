"""
Scénario combiné pour la démonstration (Clip Chrono 60 s) : une séquence courte et scénarisée
reconnaissance → attaque principale, pensée pour déclencher la chaîne détection → remédiation.

Phase 1 (reconnaissance, quelques secondes) : repérage des endpoints (GET /auth/docs, /api/docs,
tentative de pagination). Phase 2 (attaque principale) : brute-force soutenu sur un compte fictif.
Confinement : durée totale bornée, arrêt immédiat.
"""
from __future__ import annotations

import asyncio

import httpx

from .base import MAX_DURATION_S, ParamField, RunCounters, Scenario, interruptible_sleep, send
from .bruteforce import TARGET_ACCOUNTS, WRONG_PASSWORDS


class ComboScenario(Scenario):
    def __init__(self) -> None:
        super().__init__(
            id="combo",
            name="Attaque combinée (démo 60 s)",
            description="Reconnaissance rapide puis brute-force soutenu — séquence pensée pour le Clip Chrono.",
            incident_type="combo",
            defense="Chaîne complète : détection ML → blocage IP + remise en état → transaction de preuve.",
            params=[
                ParamField("recon_s", "Reconnaissance", "int", default=8, min=2, max=20, step=1, unit="s"),
                ParamField("attack_s", "Attaque principale", "int", default=40, min=10, max=MAX_DURATION_S, step=5, unit="s"),
            ],
        )

    async def run(self, client: httpx.AsyncClient, params: dict, counters: RunCounters, stop: asyncio.Event) -> None:
        # Phase 1 : reconnaissance (lecture d'endpoints publics)
        recon_end = asyncio.get_event_loop().time() + int(params["recon_s"])
        for path in ("/auth/docs", "/api/docs", "/api/transactions?limit=5"):
            if stop.is_set():
                return
            await send(client, counters, "GET", path)
            await interruptible_sleep(1.0, stop)
        while asyncio.get_event_loop().time() < recon_end and not stop.is_set():
            await interruptible_sleep(0.5, stop)

        # Phase 2 : brute-force soutenu (la durée est bornée par le superviseur de l'orchestrateur)
        i = 0
        while not stop.is_set():
            await send(client, counters, "POST", "/auth/login",
                       json={"email": TARGET_ACCOUNTS[i % len(TARGET_ACCOUNTS)], "password": WRONG_PASSWORDS[i % len(WRONG_PASSWORDS)]})
            i += 1
            await interruptible_sleep(0.2, stop)
