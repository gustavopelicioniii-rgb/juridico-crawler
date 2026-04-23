"""
Configurações centralizadas via pydantic-settings.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import Field, field_validator, AliasChoices


class Settings(BaseSettings):
    """Configurações da aplicação."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- API ---
    api_host: str = Field("0.0.0.0", validation_alias=AliasChoices("API_HOST", "api_host"))
    api_port: int = Field(8000, validation_alias=AliasChoices("API_PORT", "api_port"))
    api_debug: bool = Field(False, validation_alias=AliasChoices("API_DEBUG", "api_debug"))
    api_secret_key: str = Field("change-me-in-production", validation_alias=AliasChoices("API_SECRET_KEY", "api_secret_key"))
    api_environment: str = Field("development", validation_alias=AliasChoices("API_ENVIRONMENT", "api_environment"))
    frontend_origins: str = Field(
        "http://localhost:3333,http://localhost:5173",
        validation_alias=AliasChoices("FRONTEND_ORIGINS", "frontend_origins"),
    )

    @field_validator("api_secret_key", mode="after")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        insecure = {
            "change-me-in-production",
            "troque-por-uma-chave-segura-em-producao",
        }
        if os.getenv("API_ENVIRONMENT", "development").lower() == "production" and v in insecure:
            raise ValueError(
                "API_SECRET_KEY está com valor placeholder em produção. "
                "Gere uma chave segura (ex.: `openssl rand -hex 32`) e defina em API_SECRET_KEY."
            )
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    # --- Database ---
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/juridico_crawler"),
        validation_alias=AliasChoices("DATABASE_URL", "database_url")
    )
    database_pool_size: int = Field(10, validation_alias=AliasChoices("DATABASE_POOL_SIZE", "database_pool_size"))
    database_max_overflow: int = Field(20, validation_alias=AliasChoices("DATABASE_MAX_OVERFLOW", "database_max_overflow"))

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str = None) -> str:
        raw_v = v or os.getenv("DATABASE_URL")
        if not raw_v:
            return "postgresql+asyncpg://postgres:postgres@localhost:5432/juridico_crawler"
        raw_v = raw_v.strip()
        print(f"--- DATABASE_URL REAL: {raw_v.split('@')[-1] if '@' in raw_v else raw_v} ---")
        if raw_v.startswith("postgres://"):
            return raw_v.replace("postgres://", "postgresql+asyncpg://", 1)
        if raw_v.startswith("postgresql://") and "+asyncpg" not in raw_v:
            return raw_v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return raw_v

    # --- API Keys ---
    anthropic_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"))
    datajud_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("DATAJUD_API_KEY", "datajud_api_key"))
    datajud_base_url: str = Field("https://api-publica.datajud.cnj.jus.br", validation_alias=AliasChoices("DATAJUD_BASE_URL", "datajud_base_url"))
    firecrawl_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("FIRECRAWL_API_KEY", "firecrawl_api_key"))

    # --- Crawlers ---
    tjsp_enabled: bool = Field(True, validation_alias=AliasChoices("TJSP_ENABLED", "tjsp_enabled"))
    datajud_enabled: bool = Field(True, validation_alias=AliasChoices("DATAJUD_ENABLED", "datajud_enabled"))
    proxy_list: Optional[str] = Field(None, validation_alias=AliasChoices("PROXY_LIST", "proxy_list"))
    crawler_requests_per_minute: int = Field(120, validation_alias=AliasChoices("CRAWLER_REQUESTS_PER_MINUTE", "crawler_requests_per_minute"))
    crawler_max_retries: int = Field(3, validation_alias=AliasChoices("CRAWLER_MAX_RETRIES", "crawler_max_retries"))
    crawler_retry_delay: int = Field(5, validation_alias=AliasChoices("CRAWLER_RETRY_DELAY", "crawler_retry_delay"))

    # --- Scheduler ---
    scheduler_cron_hora: int = Field(0, validation_alias=AliasChoices("SCHEDULER_CRON_HORA", "scheduler_cron_hora"))
    scheduler_cron_minuto: int = Field(0, validation_alias=AliasChoices("SCHEDULER_CRON_MINUTO", "scheduler_cron_minuto"))


settings = Settings()
