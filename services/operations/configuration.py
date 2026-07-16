from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RuntimeConfigurationIssue:
    code: str
    field: str


class RuntimeConfigurationError(RuntimeError):
    code = "runtime_configuration_invalid"

    def __init__(self, issues: tuple[RuntimeConfigurationIssue, ...]) -> None:
        self.issues = issues
        issue_codes = ", ".join(issue.code for issue in issues)
        super().__init__(f"runtime configuration is invalid: {issue_codes}")


def validate_runtime_configuration(config: Any) -> None:
    """Reject unsafe cross-field settings before any runtime dependency is opened."""

    issues: list[RuntimeConfigurationIssue] = []
    profile = config.runtime_profile
    bootstrap_username = config.auth_bootstrap_username.strip()
    bootstrap_password = _secret_value(config.auth_bootstrap_password).strip()

    if bool(bootstrap_username) != bool(bootstrap_password):
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.bootstrap_credentials_incomplete",
                field="auth_bootstrap_username",
            )
        )

    if profile == "local":
        if config.auth_mode == "legacy-local" and not config.debug:
            issues.append(
                RuntimeConfigurationIssue(
                    code="runtime.local_legacy_requires_debug",
                    field="debug",
                )
            )
    elif profile == "production":
        _validate_production(config, issues)
    else:
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.profile_unsupported",
                field="runtime_profile",
            )
        )

    if issues:
        raise RuntimeConfigurationError(tuple(issues))


def _validate_production(
    config: Any,
    issues: list[RuntimeConfigurationIssue],
) -> None:
    requirements = (
        (
            not config.debug,
            "runtime.production_debug_disabled",
            "debug",
        ),
        (
            config.auth_mode == "accounts",
            "runtime.production_accounts_required",
            "auth_mode",
        ),
        (
            bool(config.auth_cookie_secure),
            "runtime.production_secure_cookie_required",
            "auth_cookie_secure",
        ),
        (
            config.database_migration_mode == "validate",
            "runtime.production_schema_validate_required",
            "database_migration_mode",
        ),
        (
            bool(_secret_value(config.database_url).strip()),
            "runtime.production_database_url_required",
            "database_url",
        ),
        (
            not _secret_value(config.admin_token).strip(),
            "runtime.production_shared_admin_token_forbidden",
            "admin_token",
        ),
    )
    for valid, code, field in requirements:
        if not valid:
            issues.append(RuntimeConfigurationIssue(code=code, field=field))

    origins = tuple(config.cors_origins)
    if not origins:
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.production_cors_origin_required",
                field="cors_origins",
            )
        )
    elif len(set(origins)) != len(origins) or any(
        not _is_secure_exact_origin(origin) for origin in origins
    ):
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.production_cors_origin_invalid",
                field="cors_origins",
            )
        )

    if (
        str(config.llm_provider).strip().casefold() == "deepseek"
        and not _secret_value(config.deepseek_api_key).strip()
    ):
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.production_llm_key_required",
                field="deepseek_api_key",
            )
        )


def _is_secure_exact_origin(origin: object) -> bool:
    if not isinstance(origin, str) or not origin or "*" in origin:
        return False
    try:
        parsed = urlsplit(origin)
        _ = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return False
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    try:
        return not ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return True


def _secret_value(value: object) -> str:
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        return str(getter())
    return str(value or "")
