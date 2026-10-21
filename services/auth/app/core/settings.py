"""
Configuration du service d'authentification, lue dans les variables d'environnement
(ou un fichier .env en développement). Aucune valeur sensible n'est codée ici.
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "poupal-auth"
    environment: str = "development"
    log_level: str = "INFO"

    # postgresql+psycopg://poupal_auth:<mot de passe>@db:5432/poupal
    database_url: str = Field(..., description="URL SQLAlchemy du rôle poupal_auth")

    # Origines autorisées par CORS, séparées par des virgules
    cors_origins: str = "http://localhost:8080"

    # Jetons JWT (RS256) — clés générées par scripts/gen_keys.sh
    jwt_private_key_path: str = "/run/secrets/jwt_private.pem"
    jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    jwt_issuer: str = "poupal-auth"
    jwt_expires_minutes: int = 30

    # Limitation de débit sur POST /auth/login : "5/60" = 5 essais par minute et par IP
    login_rate_limit: str = "5/60"

    # Mots de passe : longueur minimale (argon2 n'a pas de maximum pratique)
    password_min_length: int = 10

    # Données de démonstration (seed) — le mot de passe vient de l'environnement
    seed_demo_data: bool = False
    demo_password: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
