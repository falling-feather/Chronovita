"""Admin-managed local LLM configuration persisted in the classroom database."""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsError

from settings import secret_value, settings
from services import persistence

_NAMESPACE = "runtime_config"
_KEY = "llm"


class ApiConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: str = Field(pattern=r"^(?:mock|deepseek)$")
    api_key: str | None = Field(default=None, max_length=512)
    clear_api_key: bool = False
    base_url: str = Field(min_length=8, max_length=240)
    model: str = Field(min_length=1, max_length=128)
    model_pro: str = Field(min_length=1, max_length=128)
    thinking: str = Field(pattern=r"^(?:disabled|enabled|auto)$")


class ApiConfigView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    api_key_configured: bool
    api_key_last4: str
    base_url: str
    model: str
    model_pro: str
    thinking: str


def _validate_base_url(value: str) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("API 地址必须是无账号密码的 HTTPS 地址")
    return value.strip().rstrip("/")


def _view() -> ApiConfigView:
    key = secret_value(settings.deepseek_api_key).strip()
    return ApiConfigView(
        provider=settings.llm_provider,
        api_key_configured=bool(key),
        api_key_last4=key[-4:] if key else "",
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        model_pro=settings.deepseek_model_pro,
        thinking=settings.deepseek_thinking,
    )


def apply_api_config(payload: ApiConfigUpdate) -> ApiConfigView:
    base_url = _validate_base_url(payload.base_url)
    current_key = secret_value(settings.deepseek_api_key).strip()
    if payload.clear_api_key:
        api_key = ""
    elif payload.api_key is not None and payload.api_key.strip():
        api_key = payload.api_key.strip()
    else:
        api_key = current_key
    stored = {
        "provider": payload.provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": payload.model,
        "model_pro": payload.model_pro,
        "thinking": payload.thinking,
    }
    persistence.kv_set(_NAMESPACE, _KEY, stored)
    _apply(stored)
    return _view()


def load_api_config() -> None:
    stored = persistence.kv_get(_NAMESPACE, _KEY)
    if not isinstance(stored, dict):
        return
    try:
        payload = ApiConfigUpdate(
            provider=str(stored.get("provider", settings.llm_provider)),
            api_key=None,
            base_url=str(stored.get("base_url", settings.deepseek_base_url)),
            model=str(stored.get("model", settings.deepseek_model)),
            model_pro=str(stored.get("model_pro", settings.deepseek_model_pro)),
            thinking=str(stored.get("thinking", settings.deepseek_thinking)),
        )
        _validate_base_url(payload.base_url)
    except (ValueError, TypeError, SettingsError):
        return
    _apply({
        "provider": payload.provider,
        "api_key": str(stored.get("api_key", "")),
        "base_url": payload.base_url,
        "model": payload.model,
        "model_pro": payload.model_pro,
        "thinking": payload.thinking,
    })


def _apply(stored: dict[str, str]) -> None:
    from pydantic import SecretStr

    settings.llm_provider = stored["provider"]
    settings.deepseek_api_key = SecretStr(stored.get("api_key", ""))
    settings.deepseek_base_url = stored["base_url"]
    settings.deepseek_model = stored["model"]
    settings.deepseek_model_pro = stored["model_pro"]
    settings.deepseek_thinking = stored["thinking"]
