"""
Métriques Prometheus du service d'authentification (exposées sur GET /metrics).

Techniques : requêtes HTTP par route / méthode / code, histogramme de latence,
erreurs base de données. Métier : tentatives de connexion par résultat.
"""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Nombre de requêtes HTTP reçues",
    ["service", "method", "route", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Latence des requêtes HTTP",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
DB_ERRORS = Counter(
    "poupal_db_errors_total",
    "Erreurs rencontrées lors d'un accès à la base de données",
    ["service"],
)

# --- Métier (auth) ---
LOGIN_ATTEMPTS = Counter(
    "poupal_login_attempts_total",
    "Tentatives de connexion par résultat (success, failure, rate_limited)",
    ["result"],
)


def render_metrics() -> tuple[bytes, str]:
    """Corps et Content-Type de la réponse /metrics."""
    return generate_latest(), CONTENT_TYPE_LATEST
