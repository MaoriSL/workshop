"""
Configuration de l'API métier, lue dans les variables d'environnement
(ou un fichier .env en développement). Aucune valeur sensible n'est codée ici.
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "poupal-api"
    environment: str = "development"
    log_level: str = "INFO"

    # postgresql+psycopg://poupal_api:<mot de passe>@db:5432/poupal
    database_url: str = Field(..., description="URL SQLAlchemy du rôle poupal_api")

    # Origines autorisées par CORS, séparées par des virgules
    cors_origins: str = "http://localhost:8080"

    # Vérification des JWT : l'API ne possède QUE la clé publique (elle ne peut pas signer)
    jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    jwt_issuer: str = "poupal-auth"

    # Limitation de débit sur POST /api/transactions : "10/60" = 10 envois par minute et par utilisateur
    transaction_rate_limit: str = "10/60"

    # Règles métier (montants en centimes)
    max_transaction_cents: int = 500_000  # 5 000,00 €
    demo_initial_balance_cents: int = 100_000  # solde offert à la création d'un compte (démo)
    currency: str = "EUR"

    # Données de démonstration (seed)
    seed_demo_data: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
