import os
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.version import APP_VERSION


def secret_value(value: str | SecretStr) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


def runtime_env_file() -> str | None:
    disabled = os.environ.get("CHRONO_DISABLE_DOTENV", "").strip().casefold()
    if disabled in {"1", "true", "yes", "on"}:
        return None
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHRONO_", extra="ignore")

    app_name: str = "Chronovita API"
    app_version: str = APP_VERSION
    runtime_profile: Literal["local", "production"] = "local"
    api_worker_count: int = Field(default=1, ge=1, le=64)
    api_max_request_body_bytes: int = Field(
        default=4 * 1024 * 1024,
        ge=64 * 1024,
        le=64 * 1024 * 1024,
    )
    debug: bool = True
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    trusted_hosts: list[str] = ["127.0.0.1", "localhost", "testserver"]
    sqlite_path: str = "data/chronovita.db"
    database_url: SecretStr = SecretStr("")
    database_migration_mode: Literal["apply-safe", "validate"] = "apply-safe"
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=30.0, ge=1, le=300)
    database_pool_recycle_seconds: int = Field(default=1800, ge=30, le=86_400)
    database_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    database_migration_lock_timeout_seconds: float = Field(
        default=30.0,
        ge=0.1,
        le=300,
    )
    content_root: str = "content"
    admin_token: SecretStr = SecretStr("")
    admin_actor: str = "local-admin"
    auth_mode: Literal["legacy-local", "accounts"] = "legacy-local"
    auth_session_ttl_seconds: int = Field(default=8 * 60 * 60, ge=300, le=30 * 24 * 60 * 60)
    auth_cookie_name: str = Field(
        default="chronovita_session",
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]+$",
    )
    auth_cookie_secure: bool = False
    auth_login_rate_limit_attempts: int = Field(default=10, ge=1, le=1000)
    auth_login_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_login_rate_limit_max_clients: int = Field(
        default=10_000,
        ge=1,
        le=1_000_000,
    )
    practice_llm_rate_limit_requests: int = Field(default=20, ge=1, le=1000)
    practice_llm_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
    )
    practice_llm_rate_limit_max_users: int = Field(
        default=10_000,
        ge=1,
        le=1_000_000,
    )
    practice_llm_max_concurrent_per_user: int = Field(default=2, ge=1, le=20)
    practice_llm_timeout_seconds: float = Field(default=90.0, ge=5.0, le=300.0)
    practice_llm_max_response_chars: int = Field(
        default=8192,
        ge=1024,
        le=262_144,
    )
    practice_saga_ttl_seconds: int = Field(
        default=60 * 60,
        ge=60,
        le=24 * 60 * 60,
    )
    practice_saga_max_active_per_user: int = Field(default=8, ge=1, le=100)
    practice_saga_max_active_global: int = Field(
        default=5000,
        ge=1,
        le=100_000,
    )
    auth_bootstrap_username: str = ""
    auth_bootstrap_password: SecretStr = SecretStr("")
    auth_bootstrap_display_name: str = "Chronovita Admin"
    game_catalog_path: str = Field(
        default="scenarios/catalog.v1.json",
        min_length=1,
    )
    game_user_id: str = Field(
        default="local-student",
        min_length=2,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$",
    )

    # LLM 适配层
    llm_provider: str = "mock"  # mock | deepseek
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_allowed_hosts: list[str] = ["api.deepseek.com"]
    deepseek_model: str = "deepseek-v4-flash"
    # 「问 · 跨时对话」用更准的 pro 模型（saga 仍用 flash 以保证流式速度）
    deepseek_model_pro: str = "deepseek-v4-pro"
    # V4 thinking 模式：disabled / enabled / auto（默认 disabled，互动小说要快）
    deepseek_thinking: str = "disabled"
    llm_structured_timeout_seconds: float = Field(default=12.0, ge=1, le=60)
    llm_structured_max_tokens: int = Field(default=512, ge=32, le=4096)
    llm_structured_max_response_bytes: int = Field(
        default=32 * 1024,
        ge=1024,
        le=256 * 1024,
    )


settings = Settings(_env_file=runtime_env_file())
