"""Application settings, read from the environment (and the repository-root .env for local runs).

There are deliberately no default values for secrets: an unset password stays empty and the
readiness probe reports the dependency as failed rather than silently using a guessable value.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import SecretStr
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

    @property
    def database_dsn(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        return (
            f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        password = quote_plus(self.redis_password.get_secret_value())
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
