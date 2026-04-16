from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(alias="POSTGRES_DB")

    # Read-only role used only by the /ask endpoint. Credentials are fixed
    # by the 002_ro_role.sql init script; exposed via env so the compose
    # stack can override if you want a different password locally.
    postgres_ro_user: str = Field("gam_ro", alias="POSTGRES_RO_USER")
    postgres_ro_password: str = Field("gam_ro", alias="POSTGRES_RO_PASSWORD")

    redis_host: str = Field(alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")

    api_log_level: str = Field("INFO", alias="API_LOG_LEVEL")
    api_cache_ttl_seconds: int = Field(300, alias="API_CACHE_TTL_SECONDS")

    @property
    def pg_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def pg_ro_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_ro_user}:{self.postgres_ro_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
