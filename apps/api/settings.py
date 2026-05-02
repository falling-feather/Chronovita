from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHRONO_", extra="ignore")

    app_name: str = "Chronovita API"
    app_version: str = "1.9.1"
    debug: bool = True
    database_url: str = "postgresql+asyncpg://chrono:chrono@127.0.0.1:5432/chronovita"
    redis_url: str = "redis://127.0.0.1:6379/0"
    chroma_url: str = "http://127.0.0.1:8001"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    sqlite_path: str = "../../data/chronovita.db"


settings = Settings()
