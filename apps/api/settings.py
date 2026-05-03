from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHRONO_", extra="ignore")

    app_name: str = "Chronovita API"
    app_version: str = "0.1.0"
    debug: bool = True
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    sqlite_path: str = "../../data/chronovita.db"

    # LLM 适配层
    llm_provider: str = "mock"  # mock | deepseek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    # 「问 · 跨时对话」用更准的 pro 模型（saga 仍用 flash 以保证流式速度）
    deepseek_model_pro: str = "deepseek-v4-pro"
    # V4 thinking 模式：disabled / enabled / auto（默认 disabled，互动小说要快）
    deepseek_thinking: str = "disabled"


settings = Settings()
