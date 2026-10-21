"""Admin-managed local LLM configuration persisted in the classroom database."""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsError

from settings import secret_value, settings
from services import persistence
from services.content_history.publication import PublicationConfigurationError, load_repository_binding

_NAMESPACE = "runtime_config"
_KEY = "llm"
_configuration_warning = ""


class ApiConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, protected_namespaces=("model_validate", "model_dump"))

    provider: str = Field(pattern=r"^(?:mock|deepseek)$")
    api_key: str | None = Field(default=None, max_length=512)
    clear_api_key: bool = False
    base_url: str = Field(min_length=8, max_length=240)
    model: str = Field(min_length=1, max_length=128)
    model_pro: str = Field(min_length=1, max_length=128)
    thinking: str = Field(pattern=r"^(?:disabled|enabled|auto)$")
    github_publication_enabled: bool | None = None
    github_token: str | None = Field(default=None, max_length=512)
    clear_github_token: bool = False


class ApiConfigView(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=("model_validate", "model_dump"))

    provider: str
    api_key_configured: bool
    api_key_last4: str
    base_url: str
    model: str
    model_pro: str
    thinking: str
    github_publication_enabled: bool
    github_token_configured: bool
    github_token_last4: str
    github_repository: str
    github_configuration_error: str = ""
    configuration_warning: str = ""


def _validate_base_url(value: str) -> str:
    try:
        parsed = urlparse(value.strip().rstrip("/"))
        port = parsed.port
    except ValueError as exc:
        raise ValueError("API 地址无效") from exc
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or "\\" in value or port not in {None, 443}
            or any(character.isspace() for character in value.strip())):
        raise ValueError("API 地址必须是无账号密码的 HTTPS 地址")
    return value.strip().rstrip("/")


def _view() -> ApiConfigView:
    key = secret_value(settings.deepseek_api_key).strip()
    github_token = secret_value(settings.github_publication_token).strip()
    repository = ""
    binding_error = ""
    try:
        binding = load_repository_binding(settings.content_history_target_path)
        repository = f"{binding.owner}/{binding.repository}"
    except PublicationConfigurationError:
        binding_error = "课程仓库绑定缺少、损坏或尚未就绪；教师发布不可用。"
    return ApiConfigView(
        provider=settings.llm_provider,
        api_key_configured=bool(key),
        api_key_last4=key[-4:] if key else "",
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        model_pro=settings.deepseek_model_pro,
        thinking=settings.deepseek_thinking,
        github_publication_enabled=settings.github_publication_enabled,
        github_token_configured=bool(github_token),
        github_token_last4=github_token[-4:] if github_token else "",
        github_repository=repository,
        github_configuration_error=binding_error,
        configuration_warning=_configuration_warning,
    )


def apply_api_config(payload: ApiConfigUpdate) -> ApiConfigView:
    global _configuration_warning
    if payload.clear_api_key and payload.api_key:
        raise ValueError("清除密钥与录入新密钥不能同时选择")
    if payload.clear_github_token and payload.github_token:
        raise ValueError("清除仓库令牌与录入新令牌不能同时选择")
    base_url = _validate_base_url(payload.base_url)
    current_key = secret_value(settings.deepseek_api_key).strip()
    if payload.clear_api_key:
        api_key = ""
    elif payload.api_key is not None and payload.api_key.strip():
        api_key = payload.api_key.strip()
    else:
        api_key = current_key
    current_github_token = secret_value(settings.github_publication_token).strip()
    if payload.clear_github_token:
        github_token = ""
    elif payload.github_token is not None and payload.github_token.strip():
        github_token = payload.github_token.strip()
    else:
        github_token = current_github_token
    provider = "mock" if payload.clear_api_key else payload.provider
    if provider == "deepseek":
        if not api_key:
            raise ValueError("启用在线生成前请先录入 API 密钥")
        if urlparse(base_url).hostname not in settings.deepseek_allowed_hosts:
            raise ValueError("API 地址不在服务器受信任列表中")
    github_enabled = (settings.github_publication_enabled if payload.github_publication_enabled is None
                      else payload.github_publication_enabled)
    if payload.clear_github_token:
        github_enabled = False
    if github_enabled:
        if not github_token:
            raise ValueError("启用教师仓库发布前请先录入 GitHub 令牌")
        try:
            load_repository_binding(settings.content_history_target_path)
        except PublicationConfigurationError as exc:
            raise ValueError("课程仓库绑定尚未就绪，不能启用发布") from exc
    stored = {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": payload.model,
        "model_pro": payload.model_pro,
        "thinking": payload.thinking,
        "github_publication_enabled": github_enabled,
        "github_token": github_token,
    }
    persistence.kv_set(_NAMESPACE, _KEY, stored)
    _apply(stored)
    _configuration_warning = ""
    return _view()


def load_api_config() -> None:
    global _configuration_warning
    _configuration_warning = ""
    stored = persistence.kv_get(_NAMESPACE, _KEY)
    if stored is None:
        return
    try:
        if not isinstance(stored, dict):
            raise ValueError("配置不是对象")
        payload = ApiConfigUpdate(
            provider=str(stored.get("provider", settings.llm_provider)),
            api_key=stored.get("api_key", secret_value(settings.deepseek_api_key)),
            base_url=str(stored.get("base_url", settings.deepseek_base_url)),
            model=str(stored.get("model", settings.deepseek_model)),
            model_pro=str(stored.get("model_pro", settings.deepseek_model_pro)),
            thinking=str(stored.get("thinking", settings.deepseek_thinking)),
            github_publication_enabled=stored.get("github_publication_enabled", settings.github_publication_enabled),
            github_token=stored.get("github_token", secret_value(settings.github_publication_token)),
        )
        _validate_base_url(payload.base_url)
        if payload.provider == "deepseek" and (not payload.api_key or urlparse(payload.base_url).hostname not in settings.deepseek_allowed_hosts):
            raise ValueError("在线配置不完整")
        if payload.github_publication_enabled and not payload.github_token:
            raise ValueError("仓库配置不完整")
    except (ValueError, TypeError, SettingsError):
        settings.llm_provider = "mock"
        settings.github_publication_enabled = False
        _configuration_warning = "保存的 API 配置无效，已停用在线生成和教师仓库发布；请管理员重新保存。"
        return
    _apply({
        "provider": payload.provider,
        "api_key": payload.api_key or "",
        "base_url": payload.base_url,
        "model": payload.model,
        "model_pro": payload.model_pro,
        "thinking": payload.thinking,
        "github_publication_enabled": payload.github_publication_enabled,
        "github_token": payload.github_token or "",
    })


def _apply(stored: dict[str, object]) -> None:
    from pydantic import SecretStr

    settings.llm_provider = stored["provider"]
    settings.deepseek_api_key = SecretStr(stored.get("api_key", ""))
    settings.deepseek_base_url = stored["base_url"]
    settings.deepseek_model = stored["model"]
    settings.deepseek_model_pro = stored["model_pro"]
    settings.deepseek_thinking = stored["thinking"]
    settings.github_publication_enabled = bool(stored.get("github_publication_enabled", False))
    settings.github_publication_token = SecretStr(str(stored.get("github_token", "")))
