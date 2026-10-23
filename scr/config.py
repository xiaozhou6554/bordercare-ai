"""Runtime settings for the local Product Research Agent."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
_AUTH_ENABLED = os.getenv("AUTH_ENABLED")
_AUTH_DEFAULT = APP_ENV in {"production", "staging"}


@dataclass(frozen=True)
class Settings:
    project_name: str = "跨境电商选品调研 Agent"
    app_env: str = APP_ENV
    default_marketplace: str = os.getenv("DEFAULT_MARKETPLACE", "US").upper()
    default_currency: str = os.getenv("DEFAULT_CURRENCY", "USD").upper()
    default_profit_target: float = float(os.getenv("DEFAULT_PROFIT_TARGET", "0.25"))
    cache_ttl_seconds: int = int(float(os.getenv("CACHE_DEFAULT_TTL", "6")) * 3600)
    redis_url: str = os.getenv("REDIS_URL", "")
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    auth_enabled: bool = (_AUTH_ENABLED.strip().lower() in {"1", "true", "yes", "on"}) if _AUTH_ENABLED is not None else _AUTH_DEFAULT
    auth_secret: str = os.getenv("AUTH_SECRET", "")
    auth_allow_signup: bool = os.getenv("AUTH_ALLOW_SIGNUP", "false").strip().lower() in {"1", "true", "yes", "on"}
    auth_token_ttl_seconds: int = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))
    task_queue_workers: int = max(1, min(16, int(os.getenv("TASK_QUEUE_WORKERS", "2"))))
    task_timeout_seconds: int = max(60, int(os.getenv("TASK_TIMEOUT_SECONDS", "1800")))
    task_queue_role: str = os.getenv("TASK_QUEUE_ROLE", "combined").strip().lower()
    api_rate_limit_per_minute: int = max(1, int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120")))
    auth_rate_limit_per_minute: int = max(1, int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "10")))
    session_memory_ttl_seconds: int = int(os.getenv("SESSION_MEMORY_TTL_SECONDS", str(30 * 24 * 3600)))
    idempotency_ttl_seconds: int = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", str(24 * 3600)))
    crawler_delay_seconds: float = float(os.getenv("CRAWLER_DELAY_SECONDS", "2.0"))
    crawler_max_retries: int = int(os.getenv("CRAWLER_MAX_RETRIES", "3"))
    crawler_timeout_seconds: float = float(os.getenv("CRAWLER_TIMEOUT_SECONDS", "30"))
    data_mode: str = os.getenv("RESEARCH_DATA_MODE", "live").lower()
    alibaba_app_key: str = os.getenv("ALIBABA_APP_KEY", "")
    alibaba_app_secret: str = os.getenv("ALIBABA_APP_SECRET", "")
    onebound_api_key: str = os.getenv("ONEBOUND_API_KEY", "")
    onebound_api_secret: str = os.getenv("ONEBOUND_API_SECRET", "")
    onebound_1688_enabled: bool = os.getenv("ONEBOUND_1688_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
    llm_api_key: str = (os.getenv("ANTHROPIC_API_KEY", "") if os.getenv("LLM_PROVIDER", "openai_compatible").lower() == "anthropic" else os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-20250514") if os.getenv("LLM_PROVIDER", "openai_compatible").lower() == "anthropic" else os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    llm_base_url: str = os.getenv("LLM_BASE_URL", os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"))
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

    def validate_for_startup(self) -> None:
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise ValueError("APP_ENV must be development, test, staging, or production.")
        if self.task_queue_role not in {"combined", "api", "worker"}:
            raise ValueError("TASK_QUEUE_ROLE must be combined, api, or worker.")
        if self.app_env in {"staging", "production"}:
            if not self.auth_enabled:
                raise ValueError("AUTH_ENABLED must be true in staging and production.")
            if len(self.auth_secret) < 32:
                raise ValueError("AUTH_SECRET must contain at least 32 characters in staging and production.")
            if not self.database_url.startswith((
                "postgresql://", "postgres://", "postgresql+psycopg://",
                "mysql://", "mysql+pymysql://",
            )):
                raise ValueError("DATABASE_URL must use PostgreSQL or MySQL in staging and production.")
            if not self.redis_url:
                raise ValueError("REDIS_URL is required in staging and production.")
            if self.data_mode == "demo":
                raise ValueError("RESEARCH_DATA_MODE=demo is not permitted in staging or production.")


settings = Settings()
