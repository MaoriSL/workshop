"""
Tests des endpoints techniques et du contexte de requête :
/health, /ready, /metrics, en-tête X-Request-ID et format d'erreur unique.
"""
from __future__ import annotations

import uuid



def test_health_returns_ok(client, settings):
    response = client.get("/health")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "service": settings.service_name}


def test_ready_checks_database_and_secrets(client, settings):
    response = client.get("/ready")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == settings.service_name
    assert body["checks"] == {"database": True, "secrets": True}


def test_metrics_exposes_http_requests_total(client):
    client.get("/health")  # au moins une requête comptée
    response = client.get("/metrics")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text
    assert 'route="/health"' in response.text


def test_request_id_is_propagated(client):
    response = client.get("/health", headers={"X-Request-ID": "req-test-12345"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test-12345"


def test_request_id_is_generated_when_absent(client):
    response = client.get("/health")

    assert response.status_code == 200
    uuid.UUID(response.headers["X-Request-ID"])  # un UUID est généré


def test_request_id_is_returned_on_errors_too(client):
    response = client.get("/auth/me", headers={"X-Request-ID": "req-erreur-1"})

    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "req-erreur-1"


def test_unknown_route_uses_unified_error_format(client):
    response = client.get("/auth/route-inexistante")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"message", "code"}
    assert body["code"] == "http_error"
