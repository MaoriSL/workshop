"""Signature HMAC des incidents : correcte, vérifiable, et refusée si le corps est altéré."""
import hashlib
import hmac
import json

from ml.detection.service.webhook import canonical_body, send_incident, sign, verify


INCIDENT = {"incident_id": "inc-1", "state": "ANOMALIE", "score": 0.73, "top_features": [{"name": "x", "value": 1}]}


def test_signature_matches_reference_hmac():
    body = canonical_body(INCIDENT)
    expected = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert sign(body, "secret") == expected
    assert json.loads(body) == INCIDENT
    assert body == json.dumps(INCIDENT, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def test_verify_accepts_valid_and_rejects_tampered_or_missing():
    body = canonical_body(INCIDENT)
    signature = sign(body, "secret")
    assert verify(body, "secret", signature)
    assert not verify(body + b" ", "secret", signature)
    assert not verify(body, "other-secret", signature)
    assert not verify(body, "secret", None)


def test_without_url_incident_is_only_logged():
    assert send_incident(None, "secret", INCIDENT) is False
