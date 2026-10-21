"""
Règles de corrélation de sécurité (SIEM léger). Chaque règle interroge Loki (LogQL) sur une
fenêtre glissante et décide si un motif d'attaque est présent. Pas d'Elastic : on réutilise les
logs JSON déjà dans Loki (échecs de connexion, blocages WAF, accès, actions de remédiation).

Une règle = un motif + un seuil, documenté dans docs/security.md. Le seuil est réglé pour ne pas
se déclencher sur le trafic normal (générateur) mais sur les scénarios d'attaque.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Rule:
    id: str
    name: str
    description: str
    # Requête LogQL renvoyant un vecteur instantané ; chaque série = une source (ex. une IP).
    logql: str
    threshold: float
    severity: str
    incident_hint: str   # type d'incident correspondant (lien avec la remédiation)


# Note : les logs gateway/auth exposent client_ip dans la ligne JSON. On agrège par IP.
RULES = [
    Rule(
        id="bruteforce_login",
        name="Rafale d'échecs de connexion",
        description="Plus de N échecs de connexion depuis une même IP en 1 minute (brute-force probable).",
        logql='sum by (client_ip) (count_over_time({service="poupal-auth"} | json | event=~`login_failed|login_rate_limited` [1m]))',
        threshold=10,
        severity="high",
        incident_hint="bruteforce",
    ),
    Rule(
        id="waf_block_burst",
        name="Rafale de blocages WAF",
        description="Plus de N requêtes bloquées par le WAF en 1 minute (balayage d'injections).",
        logql=r'sum by (client_ip) (count_over_time({service="poupal-waf"} |= `ModSecurity: Access denied` | regexp `\[client (?P<client_ip>[0-9.]+)\]` [1m]))',
        threshold=8,
        severity="high",
        incident_hint="injection",
    ),
    Rule(
        id="enumeration",
        name="Énumération / exfiltration",
        description="Volume anormal de lectures 404 sur des identifiants de transaction (énumération).",
        logql='sum by (client_ip) (count_over_time({service="poupal-gateway"} | json | route=`/api/transactions/{transaction_id}` | status=`404` [1m]))',
        threshold=30,
        severity="medium",
        incident_hint="exfiltration",
    ),
    Rule(
        id="rate_limited_burst",
        name="Saturation (limitation de débit)",
        description="Nombre élevé de réponses 429 (la gateway limite une source agressive) : surcharge.",
        logql='sum by (client_ip) (count_over_time({service="poupal-gateway"} | json | status=`429` [1m]))',
        threshold=20,
        severity="medium",
        incident_hint="surcharge",
    ),
]
