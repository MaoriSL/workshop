"""
Métriques Prometheus de l'API métier (exposées sur GET /metrics).

Techniques : requêtes HTTP par route / méthode / code, histogramme de latence,
erreurs base de données. Métier : transactions par statut et montants (centimes).
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

# --- Métier (paiements) ---
TRANSACTIONS = Counter(
    "poupal_transactions_total",
    "Transactions créées par statut (completed, failed, pending)",
    ["status"],
)
TRANSACTION_AMOUNT = Histogram(
    "poupal_transaction_amount_cents",
    "Montant des transactions en centimes",
    buckets=(100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 250000, 500000),
)


def render_metrics() -> tuple[bytes, str]:
    """Corps et Content-Type de la réponse /metrics."""
    return generate_latest(), CONTENT_TYPE_LATEST
