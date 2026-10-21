"""
Politique de décision : un TYPE d'incident (jamais une commande) → un plan d'action pris dans
un catalogue FIXE, par escalade. Le niveau suivant n'est tenté que si la vérification échoue.

Deux familles de réponses (le sujet y tient) :
  - RESTAURER LA DISPONIBILITÉ : le service est tombé ou sature → redémarrer, recréer, bloquer l'IP…
  - TRAITER UNE COMPROMISSION / CORRUPTION : le conteneur ou les données ne sont plus dignes de
    confiance → recréer depuis l'image d'origine, restaurer la base. Un simple redémarrage serait
    une fausse réponse.
Détail et justifications : docs/remediation.md.
"""
from __future__ import annotations

INCIDENT_TYPES = ("indisponibilite", "surcharge", "bruteforce", "db_lente", "compromission", "incoherence", "inconnu")
SERVICES = ("front", "auth", "api", "db", "gateway")

# Services du détecteur (poupal-api…) → services compose (api…)
DETECTOR_SERVICE_ALIASES = {f"poupal-{s}": s for s in SERVICES}

AVAILABILITY, INTEGRITY = "disponibilite", "integrite"


def normalize_service(name: str) -> str | None:
    name = (name or "").strip().lower()
    if name in SERVICES:
        return name
    return DETECTOR_SERVICE_ALIASES.get(name)


def family(incident_type: str) -> str:
    """Famille de réponse : disponibilité ou intégrité (compromission / corruption)."""
    return INTEGRITY if incident_type in ("compromission", "incoherence") else AVAILABILITY


def build_plan(incident_type: str, service: str) -> list[dict]:
    """Plan ordonné (niveau 1 → 3). Chaque étape = un ou plusieurs playbooks de la liste blanche."""
    if incident_type == "indisponibilite":
        return [
            {"level": 1, "action": "restart_service", "params": {"service": service}, "why": "restaurer la disponibilité au moindre coût"},
            {"level": 2, "action": "recreate_service", "params": {"service": service}, "why": "conteneur peut-être corrompu : repartir de l'image d'origine"},
            {"level": 3, "action": "rollback", "params": {"service": service, "image_tag": "previous"}, "why": "l'image courante est suspecte : version précédente"},
        ]
    if incident_type == "surcharge":
        target = service if service in ("api", "auth", "gateway") else "gateway"
        return [
            {"level": 1, "action": "block_ip", "params": {"ip": "@aggressive"}, "why": "couper la source la plus agressive (logs de la gateway)"},
            {"level": 2, "action": "restart_service", "params": {"service": target}, "why": "libérer les ressources saturées"},
            {"level": 3, "action": "recreate_service", "params": {"service": target}, "why": "conteneur dégradé : image d'origine"},
        ]
    if incident_type == "bruteforce":
        return [
            {"level": 1, "action": "block_ip", "params": {"ip": "@aggressive"}, "why": "bloquer l'IP qui multiplie les échecs de connexion"},
            {"level": 2, "action": "restart_service", "params": {"service": "auth"}, "why": "remettre le service d'authentification en état"},
        ]
    if incident_type == "db_lente":
        return [
            {"level": 1, "action": "terminate_long_queries", "params": {"max_seconds": "5"}, "why": "lever les verrous / requêtes longues sans redémarrer la base"},
            {"level": 2, "action": "restart_service", "params": {"service": "db"}, "why": "base bloquée : redémarrage"},
            {"level": 3, "action": "restore_db", "params": {}, "why": "données suspectes : dernière sauvegarde valide + contrôle de cohérence"},
        ]
    if incident_type == "compromission":
        target = service if service != "db" else "api"
        return [
            {"level": 1, "action": "block_ip+recreate_service", "params": {"ip": "@aggressive", "service": target}, "why": "couper l'attaquant et repartir d'une image saine (pas un simple redémarrage)"},
            {"level": 2, "action": "restore_db", "params": {}, "why": "données possiblement altérées : restauration + contrôle de cohérence"},
        ]
    if incident_type == "incoherence":
        return [
            {"level": 1, "action": "restore_db", "params": {}, "why": "soldes incohérents : dernière sauvegarde valide"},
            {"level": 2, "action": "rollback", "params": {"service": "api", "image_tag": "previous"}, "why": "l'API courante corrompt peut-être les données"},
        ]
    return [  # inconnu
        {"level": 1, "action": "restart_service", "params": {"service": service}, "why": "réponse générique : redémarrer le service suspecté"},
        {"level": 2, "action": "recreate_service", "params": {"service": service}, "why": "puis repartir de l'image d'origine"},
    ]


def describe(plan: list[dict]) -> str:
    return " → ".join(f"{p['level']}. {p['action']}" for p in plan)
