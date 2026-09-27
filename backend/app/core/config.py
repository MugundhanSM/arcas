from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    # Application metadata
    APP_NAME: str = "ARCAS"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "ARCAS - Agentic Review & Code Analysis System. "
        "Multi-agent code review and refactoring."
    )

    DEBUG: bool = False

    API_PREFIX: str = "/api/v1"

    # Persistence
    DATABASE_URL: str = (
        "postgresql://arcas_user:arcas_password@localhost:5432/arcas"
    )

    # LLM endpoint
    LLM_API_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: int = 120

    # max parallel LLM calls across the process
    LLM_MAX_CONCURRENCY: int = 4

    AUTH_REQUIRED: bool = False
    JWT_SECRET: str = "change-me-in-production-please-rotate-this-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # Per-identity rate limiting. Requests allowed per window.
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Session memory / cache.
    REDIS_URL: str = ""
    SESSION_TTL_SECONDS: int = 3600

    # LangGraph checkpointing.
    ENABLE_CHECKPOINTING: bool = True
    CHECKPOINT_DB_PATH: str = "./arcas_checkpoints.db"

    # Result cache.
    ENABLE_RESULT_CACHE: bool = True
    RESULT_CACHE_TTL_SECONDS: int = 10_800

    # Knowledge & RAG.
    ENABLE_CHROMADB: bool = True
    CHROMADB_PATH: str = "./.chroma"

    # Observability. OpenTelemetry is optional / no-op by default.
    ENABLE_TELEMETRY: bool = True
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    # Input guardrails.
    ENABLE_INJECTION_LLM_CHECK: bool = False
    # Plant a canary token in every agent system prompt and check model output for it.
    ENABLE_CANARY_TOKENS: bool = True

    # Output guardrails
    SELFCHECK_SAMPLES: int = 0  # 0 disables multi-sample consistency checks
    # SelfCheckGPT hallucination detection.
    ENABLE_SELFCHECK: bool = False

    # Audit logging
    AUDIT_LOG_PATH: str = "./audit.log"

    # Guardrails
    MAX_CODE_SIZE_BYTES: int = 200_000

    # CORS - comma separated list of allowed origins
    CORS_ORIGINS: str = (
        "http://localhost:5173,"
        "http://localhost:3000,"
        "http://127.0.0.1:5173"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.LLM_API_URL and self.LLM_API_KEY
        )


settings = Settings()
