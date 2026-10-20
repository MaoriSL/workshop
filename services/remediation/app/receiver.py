"""
Réception des incidents : validation STRICTE du contenu (Pydantic, listes blanches fermées)
et vérification de la signature HMAC-SHA256 (contrat : docs/api/incident.md).
Tout incident non signé, mal signé ou hors contrat est refusé : personne d'autre que le
détecteur ne peut déclencher une remédiation.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .policy import INCIDENT_TYPES, normalize_service

SIGNATURE_HEADER = "X-Poupal-Signature"


def verify_signature(body: bytes, secret: str, signature: str | None) -> bool:
    """HMAC recalculé sur les octets reçus, comparaison en temps constant."""
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class TopFeature(BaseModel):
    name: str = Field(max_length=200)
    value: float
    baseline: float
    deviation: float


class IncidentIn(BaseModel):
    """Corps d'un incident envoyé par le détecteur."""
    incident_id: str = Field(min_length=4, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    state: Literal["ANOMALIE", "NORMAL"]
    detected_at: datetime
    resolved_at: datetime | None = None
    score: float
    threshold: float | None = None
    suspected_service: str = Field(max_length=40)
    incident_type: str = Field(max_length=40)
    top_features: list[TopFeature] = Field(default_factory=list, max_length=10)
    model_version: str | None = Field(default=None, max_length=40)

    @field_validator("suspected_service")
    @classmethod
    def service_in_whitelist(cls, value: str) -> str:
        if value == "inconnu":
            return value
        normalized = normalize_service(value)
        if normalized is None:
            raise ValueError(f"service inconnu : {value!r} (liste blanche : front, auth, api, db, gateway)")
        return normalized

    @field_validator("incident_type")
    @classmethod
    def type_in_catalogue(cls, value: str) -> str:
        if value not in INCIDENT_TYPES:
            raise ValueError(f"type d'incident hors catalogue : {value!r}")
        return value
