"""Application settings, read from the environment (and the repository-root .env for local runs).

There are deliberately no default values for secrets: an unset password stays empty and the
readiness probe reports the dependency as failed rather than silently using a guessable value.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, field_validator
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

    # Market-data provider keys (P08-T03). Empty means the provider is not configured; keys come
    # from the environment or a secret manager, never from source, and never appear in logs.
    # `fake` serves deterministic demo prices with no network (local development).
    market_data_mode: Literal["real", "fake"] = "real"
    coingecko_api_key: SecretStr = SecretStr("")
    twelvedata_api_key: SecretStr = SecretStr("")
    exchangerate_api_key: SecretStr = SecretStr("")
    # FX for the reporting currency (P11-T03, DEC-25..27). Providers are asked in this order; one
    # without a key is left out. The ECB needs no key.
    fx_provider_order: list[Literal["ecb", "exchangerate_api", "twelvedata"]] = [
        "ecb",
        "exchangerate_api",
        "twelvedata",
    ]
    fx_pivot_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    # Rate status (DEC-26): a rate is current for the first hours, then cached, then stale.
    # Daily publishers (the ECB) and hourly ones (the commercial API) have their own windows.
    fx_daily_current_hours: int = Field(default=36, ge=1)
    fx_daily_cached_hours: int = Field(default=72, ge=1)
    fx_hourly_current_hours: int = Field(default=2, ge=1)
    fx_hourly_cached_hours: int = Field(default=24, ge=1)
    # At most one provider refresh per window, whoever asks (schedule or users).
    fx_refresh_window_minutes: int = Field(default=15, ge=1)
    fx_refresh_per_user_per_hour: int = Field(default=5, ge=1)
    fx_status_cache_seconds: int = Field(default=60, ge=0)
    # The commercial plan's monthly request quota (ExchangeRate-API Pro: 30,000).
    fx_monthly_request_budget: int = Field(default=30_000, ge=1)

    # Message broker for the background workers (P08-T04). Credentials come from the environment.
    rabbitmq_user: str = ""
    rabbitmq_password: SecretStr = SecretStr("")
    rabbitmq_host: str = "127.0.0.1"
    rabbitmq_port: int = 5673

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
    # Analytics response cache (P06-T09): "redis" in deployments, "memory" per process (tests),
    # "off" to compute every time. Entries expire after `analytics_cache_seconds`.
    analytics_cache: Literal["redis", "memory", "off"] = "redis"
    analytics_cache_seconds: int = 300
    rate_limit_auth_requests: int = 10
    rate_limit_auth_window_seconds: int = 60
    rate_limit_auth_failures: int = 10
    rate_limit_auth_failure_window_seconds: int = 300
    rate_limit_ip_requests: int = 600
    rate_limit_ip_window_seconds: int = 60
    rate_limit_user_requests: int = 120
    rate_limit_user_window_seconds: int = 60
    max_request_body_bytes: int = 1_048_576
    # AI tool layer (P10-T02, ADR-0017): per-user call budget, per-call timeout and result size.
    ai_tool_calls_per_minute: int = 60
    ai_tool_timeout_seconds: float = 10.0
    ai_tool_max_result_bytes: int = 32_768
    # LLM providers (P10-T05, ADR-0017). Models are configuration; there is no default model.
    # "fake" needs nothing; the others need their key and model id.
    ai_provider: Literal["fake", "openai", "anthropic"] = "fake"
    ai_fallback_provider: Literal["", "fake", "openai", "anthropic"] = ""
    openai_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    ai_openai_model: str = ""
    ai_anthropic_model: str = ""
    ai_request_timeout_seconds: float = 60.0
    ai_max_output_tokens: int = 1024
    # Conversation history is deleted this many days after its last message (ADR-0017: 90).
    ai_conversation_retention_days: int = Field(default=90, ge=1, le=3650)
    # The assistant's limits (P10-T06): questions per user per rolling 24 hours, tool calls and
    # model rounds per question, earlier messages sent as context.
    ai_questions_per_day: int = Field(default=30, ge=1)
    ai_max_tool_calls_per_question: int = Field(default=20, ge=1)
    ai_max_model_rounds: int = Field(default=8, ge=2)
    ai_history_messages: int = Field(default=12, ge=0)
    # An answer that fails the checks goes back to the model this many times, then is refused.
    ai_max_answer_retries: int = Field(default=1, ge=0, le=3)
    # Tool data older than this is flagged as stale in the answer.
    ai_stale_after_hours: int = Field(default=48, ge=1)
    # Browser origins allowed to call the API. Empty (the default) disables CORS: the mobile apps
    # do not need it. A wildcard is never accepted.
    cors_allowed_origins: list[str] = []

    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_connect_timeout_seconds: float = 5.0

    @property
    def broker_url(self) -> str:
        """AMQP URL for Celery. Contains the password: never log it."""
        user = quote_plus(self.rabbitmq_user)
        password = quote_plus(self.rabbitmq_password.get_secret_value())
        return f"amqp://{user}:{password}@{self.rabbitmq_host}:{self.rabbitmq_port}//"

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
