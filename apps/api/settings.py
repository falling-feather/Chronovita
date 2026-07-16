from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHRONO_", extra="ignore")

    app_name: str = "Chronovita API"
    app_version: str = "0.9.5"
    debug: bool = True
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    sqlite_path: str = "data/chronovita.db"
    content_root: str = "content"
    admin_token: str = ""
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
    auth_bootstrap_username: str = ""
    auth_bootstrap_password: str = ""
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
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
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


settings = Settings()
