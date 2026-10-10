"""Application settings, read from the environment (and the repository-root .env for local runs).

There are deliberately no default values for secrets: an unset password stays empty and the
readiness probe reports the dependency as failed rather than silently using a guessable value.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, extra="ignore", case_sensitive=False)

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    postgres_user: str = ""
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = ""
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433

    redis_password: SecretStr = SecretStr("")
    redis_host: str = "127.0.0.1"
    redis_port: int = 6380

    readiness_timeout_seconds: float = 2.0
    otel_service_name: str = "wealthsphere-api"
    otel_exporter_otlp_endpoint: str = ""
    otel_metric_export_interval_ms: int = 15000
    metrics_token: SecretStr = SecretStr("")

    # OIDC (Keycloak). The issuer must match the `iss` claim exactly; with no issuer set, every
    # protected endpoint answers 401 (fail closed).
    oidc_issuer: str = ""
    oidc_audience: str = "wealthsphere-api"
    oidc_authorized_parties: str = "wealthsphere-mobile"
    oidc_jwks_url: str = ""
    jwks_cache_seconds: int = 300
    auth_leeway_seconds: int = 30

    # API protection (P04-T05): requests per window, counted per client IP or per account.
    # `rate_limit_storage=memory` keeps counters per process (tests; single-instance only).
    rate_limit_enabled: bool = True
    rate_limit_storage: Literal["redis", "memory"] = "redis"
    rate_limit_auth_requests: int = 10
    rate_limit_auth_window_seconds: int = 60
    rate_limit_auth_failures: int = 10
    rate_limit_auth_failure_window_seconds: int = 300
    rate_limit_ip_requests: int = 600
    rate_limit_ip_window_seconds: int = 60
    rate_limit_user_requests: int = 120
    rate_limit_user_window_seconds: int = 60
    max_request_body_bytes: int = 1_048_576
    # Browser origins allowed to call the API. Empty (the default) disables CORS: the mobile apps
    # do not need it. A wildcard is never accepted.
    cors_allowed_origins: list[str] = []

    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_connect_timeout_seconds: float = 5.0

    @property
    def database_dsn(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        return (
            f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )

    @property
    def sqlalchemy_url(self) -> str:
        """Async SQLAlchemy URL (asyncpg driver). Contains credentials: never log it."""
        return self.database_dsn.replace("postgresql://", "postgresql+asyncpg://", 1)

    @property
    def redis_url(self) -> str:
        password = quote_plus(self.redis_password.get_secret_value())
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @property
    def jwks_url(self) -> str:
        if self.oidc_jwks_url:
            return self.oidc_jwks_url
        return (
            f"{self.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs"
            if self.oidc_issuer
            else ""
        )

    @property
    def authorized_parties(self) -> frozenset[str]:
        return frozenset(p.strip() for p in self.oidc_authorized_parties.split(",") if p.strip())

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production"

    @property
    def hsts_enabled(self) -> bool:
        """Deployed environments are served over TLS only."""
        return self.environment in ("staging", "production")

    @field_validator("cors_allowed_origins")
    @classmethod
    def _explicit_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if "*" in origin or not origin.startswith(
                ("https://", "http://localhost", "http://127.0.0.1")
            ):
                raise ValueError(f"CORS origin must be an explicit https origin: {origin!r}")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
