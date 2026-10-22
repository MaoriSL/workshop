"""
Garde-fou de PÉRIMÈTRE : la console refuse d'attaquer autre chose que notre plateforme.

La cible (variable d'environnement TARGET_URL, par défaut la gateway de la plateforme) doit
résoudre vers `localhost` ou une adresse d'une plage PRIVÉE autorisée (RFC 1918 + lien local +
boucle locale, plus les CIDR passés dans ATTACK_ALLOWED_CIDRS). Toute autre cible — une IP
publique, un nom qui résout hors de ces plages — est refusée avec un message clair, et la
console démarre en mode « hors périmètre » : aucun scénario n'est lançable.

C'est la traduction en code de la règle du sujet : attaques limitées à nos machines, jamais le
réseau du campus, un autre groupe, un service tiers ou Internet.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

# Plages autorisées par défaut : boucle locale, RFC 1918 (réseaux privés), lien local.
# On peut en ajouter via ATTACK_ALLOWED_CIDRS (ex. "192.168.137.0/24") — jamais d'IP publique.
DEFAULT_ALLOWED = ["127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fc00::/7", "fe80::/10"]


def allowed_networks() -> list[ipaddress._BaseNetwork]:
    extra = [c.strip() for c in os.environ.get("ATTACK_ALLOWED_CIDRS", "").split(",") if c.strip()]
    networks: list[ipaddress._BaseNetwork] = []
    for cidr in DEFAULT_ALLOWED + extra:
        try:
            networks.append(ipaddress.ip_network(cidr))
        except ValueError:
            continue
    return networks


def resolve_host(host: str) -> list[ipaddress._BaseAddress]:
    """Toutes les adresses IP vers lesquelles le nom d'hôte résout (vide si résolution impossible)."""
    try:
        ipaddress.ip_address(host)
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return addresses


def check_target(url: str) -> tuple[bool, str]:
    """
    (autorisé, raison). Autorisé seulement si TOUTES les adresses résolues sont dans une plage
    autorisée (si une seule sort du périmètre, on refuse : pas d'attaque possible sur une cible
    ambiguë). Un nom qui ne résout pas est refusé.
    """
    parsed = urlparse(url if "://" in url else f"http://{url}")
    if parsed.scheme not in ("http", "https"):
        return False, "Cible invalide : seuls HTTP et HTTPS sont autorisés."
    if parsed.username or parsed.password:
        return False, "Cible invalide : les identifiants intégrés dans l'URL sont interdits."
    if parsed.query or parsed.fragment:
        return False, "Cible invalide : les paramètres et fragments d'URL sont interdits."
    host = parsed.hostname
    if not host:
        return False, "Cible invalide : aucun hôte."
    if host in ("localhost", "localhost.localdomain"):
        return True, "localhost (périmètre local)."
    addresses = resolve_host(host)
    if not addresses:
        return False, f"Cible « {host} » : nom non résolu, refusée par précaution."
    networks = allowed_networks()
    outside = [str(a) for a in addresses if not any(a in n for n in networks)]
    if outside:
        return False, f"Cible « {host} » hors plage privée autorisée (adresses : {', '.join(outside)}). Attaques désactivées."
    return True, f"Cible « {host} » dans la plage privée autorisée ({', '.join(str(a) for a in addresses)})."


TARGET_URL = os.environ.get("TARGET_URL", "http://gateway:80").rstrip("/")


def normalize_target(url: str) -> str:
    """Normalise une cible saisie dans la console sans modifier son hôte ni son port."""
    value = url.strip()
    if not value:
        raise ValueError("Cible vide.")
    normalized = value if "://" in value else f"http://{value}"
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Cible invalide : indiquez une adresse HTTP/HTTPS, par exemple http://192.168.1.20:18080.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Cible invalide : identifiants, paramètres et fragments interdits.")
    return normalized.rstrip("/")
