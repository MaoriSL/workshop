"""Le service démarre même si Prometheus n'est pas encore prêt : /health répond, /ready est à false."""
import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient

MODELS = Path(__file__).resolve().parents[1] / "models"


def load_app(monkeypatch, model_dir: Path):
    monkeypatch.setenv("PROMETHEUS_URL", "http://127.0.0.1:9")      # port fermé : injoignable
    monkeypatch.setenv("MODEL_DIR", str(model_dir))
    monkeypatch.setenv("DETECTOR_INTERVAL_S", "60")
    import ml.detection.service.app as module
    return importlib.reload(module)


def test_starts_without_prometheus_and_reports_not_ready(monkeypatch, tmp_path):
    module = load_app(monkeypatch, tmp_path)                        # pas de modèle non plus
    with TestClient(module.app) as client:
        assert client.get("/health").status_code == 200
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["checks"] == {"model": False, "prometheus": False}
        status = client.get("/status").json()
        assert status["state"] == "NORMAL" and status["score"] is None
        assert client.get("/incidents").json()["count"] == 0
        metrics = client.get("/metrics").text
        assert "poupal_anomaly_state 0.0" in metrics
        assert "poupal_detector_model_loaded 0.0" in metrics


def test_model_loads_when_present(monkeypatch):
    if not (MODELS / "model.joblib").exists():
        import pytest
        pytest.skip("modèle non entraîné")
    module = load_app(monkeypatch, MODELS)
    with TestClient(module.app) as client:
        checks = client.get("/ready").json()["checks"]
        assert checks["model"] is True and checks["prometheus"] is False
        assert client.get("/status").json()["threshold"] is not None
