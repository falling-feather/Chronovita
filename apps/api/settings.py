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


settings = Settings()
