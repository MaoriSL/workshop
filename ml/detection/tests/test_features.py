"""features.py doit donner EXACTEMENT le même résultat à l'entraînement (historique complet)
et en temps réel (tampon glissant des dernières minutes)."""
import numpy as np
import pandas as pd

from ml.detection.features import DEFAULT_WINDOW, build_features, latest_features, select_raw_columns, service_of
from ml.detection.model import rule_based_type


def make_raw(n: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-10-20T08:00:00Z", periods=n, freq="5s")
    return pd.DataFrame(
        {
            "http_requests_per_second_rate1m__poupal-api": rng.normal(5, 1, n),
            "http_error_ratio_5xx_rate1m__poupal-api": rng.uniform(0, 0.02, n),
            "http_latency_seconds_p95__poupal-auth": rng.normal(0.05, 0.01, n),
            "transactions_per_minute__completed": rng.poisson(3, n).astype(float),
            "transactions_per_minute__failed": rng.poisson(0.2, n).astype(float),
            "container_memory_bytes__api": rng.normal(7e7, 1e6, n),
            "container_memory_bytes__grafana": rng.normal(1e8, 1e6, n),  # ignoré (pas un service suivi)
            "service_up__api": np.ones(n),
        },
        index=index,
    )


def test_training_and_realtime_are_identical():
    raw = make_raw()
    full = build_features(raw)
    expected = list(full.columns)
    # Temps réel : tampon des `window` derniers pas, recalculé à chaque instant
    for end in range(DEFAULT_WINDOW, len(raw) + 1):
        buffer = raw.iloc[end - DEFAULT_WINDOW:end]
        live = latest_features(buffer, expected)
        pd.testing.assert_series_equal(live, full.iloc[end - 1], check_names=False)


def test_no_nan_and_expected_columns():
    full = build_features(make_raw())
    assert not full.isna().any().any()
    assert "http_requests_per_second_rate1m__poupal-api__mean12" in full.columns
    assert "http_requests_per_second_rate1m__poupal-api__diff" in full.columns
    assert "ratio_failed_transactions" in full.columns
    assert "container_memory_bytes__grafana" not in full.columns


def test_siem_security_signals_are_model_features():
    raw = make_raw()
    raw["siem_waf_block_sources"] = 0.0
    raw["siem_enumeration_sources"] = 0.0
    raw["siem_rate_limited_sources"] = 0.0
    raw["siem_bruteforce_sources"] = 1.0
    full = build_features(raw)
    assert "siem_waf_block_sources" in full.columns
    assert "siem_enumeration_sources__diff" in full.columns
    assert full["siem_bruteforce_sources"].iloc[-1] == 1.0
    assert rule_based_type(full.iloc[-1], full.iloc[-1]) == "bruteforce"


def test_missing_column_is_filled_with_zero():
    raw = make_raw()
    expected = list(build_features(raw).columns)
    without = raw.drop(columns=["http_latency_seconds_p95__poupal-auth"])
    live = latest_features(without, expected)
    assert live["http_latency_seconds_p95__poupal-auth"] == 0.0
    assert list(live.index) == expected


def test_service_attribution():
    assert service_of("http_latency_seconds_p95__poupal-api") == "poupal-api"
    assert service_of("container_memory_bytes__db") == "poupal-db"
    assert service_of("login_failures_per_minute__poupal-auth") == "poupal-auth"
    assert service_of("gateway_active_connections__poupal-gateway") == "poupal-gateway"
    assert select_raw_columns(["foo__bar"]) == []
