"""
Brute-force d'authentification : essais répétés de connexion sur un compte fictif avec une
petite liste de mots de passe erronés.

Effet attendu : rafale d'échecs (401) puis limitation (429) côté auth → détection « brute-force ».
Défense attendue : limitation de débit sur /auth/login ; blocage de l'IP par la remédiation.
Confinement : cadence et durée bornées ; cible = comptes de démonstration fictifs.
"""
from __future__ import annotations

import asyncio

import httpx

from .base import MAX_DURATION_S, ParamField, RunCounters, Scenario, interruptible_sleep, send

# Mots de passe manifestement faux (jamais le vrai) : on démontre l'échec, pas un contournement.
WRONG_PASSWORDS = ["123456", "password", "azerty123", "admin2024", "poupal123", "qwerty!!", "motdepasse", "000000demo"]
TARGET_ACCOUNTS = ["alex@poupal.demo", "victime@poupal.demo"]


class BruteForceScenario(Scenario):
    def __init__(self) -> None:
        super().__init__(
            id="bruteforce",
            name="Brute-force d'authentification",
            description="Tentatives répétées de connexion sur un compte fictif avec de faux mots de passe.",
            incident_type="bruteforce",
            defense="Limitation de débit sur /auth/login (401 génériques puis 429) et blocage de l'IP par la remédiation.",
            params=[
                ParamField("rate_per_s", "Tentatives / seconde", "int", default=20, min=1, max=100, step=5),
                ParamField("duration_s", "Durée", "int", default=60, min=5, max=MAX_DURATION_S, step=5, unit="s"),
            ],
        )

    async def run(self, client: httpx.AsyncClient, params: dict, counters: RunCounters, stop: asyncio.Event) -> None:
        interval = 1.0 / max(1, int(params["rate_per_s"]))
        i = 0
        while not stop.is_set():
            email = TARGET_ACCOUNTS[i % len(TARGET_ACCOUNTS)]
            password = WRONG_PASSWORDS[i % len(WRONG_PASSWORDS)]
            await send(client, counters, "POST", "/auth/login", json={"email": email, "password": password})
            i += 1
            await interruptible_sleep(interval, stop)
