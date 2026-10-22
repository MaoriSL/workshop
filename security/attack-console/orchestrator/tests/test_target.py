"""La console refuse toute cible hors de la plage privée autorisée (règle de confinement)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from orchestrator.app.target import check_target, normalize_target


def test_localhost_and_private_are_allowed():
    for url in ("http://localhost:8088", "http://127.0.0.1", "http://192.168.1.5", "http://10.1.2.3", "http://172.16.0.9"):
        ok, _ = check_target(url)
        assert ok, url


def test_public_targets_are_refused():
    for url in ("http://8.8.8.8", "http://1.1.1.1", "http://93.184.216.34"):
        ok, reason = check_target(url)
        assert not ok, url
        assert reason


def test_unresolvable_host_is_refused():
    ok, reason = check_target("http://cible-inexistante-poupal-xyz.invalid")
    assert not ok and "non résolu" in reason


def test_target_url_is_normalized_for_remote_demo():
    assert normalize_target("192.168.1.20:18080") == "http://192.168.1.20:18080"


def test_unsafe_target_url_is_rejected():
    for url in ("ftp://192.168.1.20", "http://user:password@192.168.1.20", "http://192.168.1.20/path?x=1"):
        ok, _ = check_target(url)
        assert not ok, url
