"""Garde-fous de l'orchestrateur : liste blanche de scénarios, bornage des paramètres."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from scenarios import SCENARIOS
from scenarios.base import MAX_CONCURRENCY, MAX_DURATION_S


def test_only_whitelisted_scenarios():
    assert set(SCENARIOS) == {"dos", "bruteforce", "injection", "exfiltration", "combo"}


def test_params_are_clamped_to_bounds():
    dos = SCENARIOS["dos"]
    clamped = dos.clamp({"concurrency": 99999, "duration_s": -5})
    assert clamped["concurrency"] <= MAX_CONCURRENCY
    assert 5 <= clamped["duration_s"] <= MAX_DURATION_S
    assert dos.clamp({"concurrency": "DROP TABLE"})["concurrency"] == 20


def test_unknown_param_is_ignored():
    bf = SCENARIOS["bruteforce"]
    out = bf.clamp({"rate_per_s": 5, "commande": "rm -rf /"})
    assert "commande" not in out and out["rate_per_s"] == 5


def test_scenarios_declare_incident_type():
    assert {s.incident_type for s in SCENARIOS.values()} == {"surcharge", "bruteforce", "injection", "exfiltration", "combo"}
