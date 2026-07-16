from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


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
    trusted_hosts_valid = _validate_exact_trusted_hosts(config, issues)

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
        if (
            trusted_hosts_valid
            and config.auth_mode == "legacy-local"
            and any(not _is_local_host(host) for host in config.trusted_hosts)
        ):
            issues.append(
                RuntimeConfigurationIssue(
                    code="runtime.local_legacy_trusted_host_invalid",
                    field="trusted_hosts",
                )
            )
    elif profile == "production":
        _validate_production(config, issues, trusted_hosts_valid=trusted_hosts_valid)
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
    *,
    trusted_hosts_valid: bool,
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

    database_url = _secret_value(config.database_url).strip()
    if database_url:
        _validate_production_database_url(database_url, issues)

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

    if trusted_hosts_valid and any(
        _is_local_host(host) for host in config.trusted_hosts
    ):
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.production_trusted_host_invalid",
                field="trusted_hosts",
            )
        )


def _validate_production_database_url(
    raw_url: str,
    issues: list[RuntimeConfigurationIssue],
) -> None:
    try:
        url = make_url(raw_url)
    except (ArgumentError, TypeError, ValueError):
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.production_database_url_invalid",
                field="database_url",
            )
        )
        return
    if (
        url.get_backend_name() != "postgresql"
        or url.drivername not in {"postgresql", "postgresql+psycopg"}
    ):
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.production_postgres_required",
                field="database_url",
            )
        )
        return
    sslmode = url.query.get("sslmode")
    if not isinstance(sslmode, str) or sslmode.casefold() != "verify-full":
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.production_database_tls_required",
                field="database_url",
            )
        )


def _validate_exact_trusted_hosts(
    config: Any,
    issues: list[RuntimeConfigurationIssue],
) -> bool:
    hosts = tuple(config.trusted_hosts)
    if not hosts:
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.trusted_host_required",
                field="trusted_hosts",
            )
        )
        return False
    canonical = tuple(str(host).casefold() for host in hosts)
    if len(set(canonical)) != len(hosts) or any(
        not _is_exact_host(host) for host in hosts
    ):
        issues.append(
            RuntimeConfigurationIssue(
                code="runtime.trusted_host_invalid",
                field="trusted_hosts",
            )
        )
        return False
    return True


def _is_exact_host(host: object) -> bool:
    if not isinstance(host, str):
        return False
    candidate = host.strip()
    if (
        not candidate
        or candidate != host
        or candidate != candidate.casefold()
        or "*" in candidate
        or "://" in candidate
        or "/" in candidate
    ):
        return False
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        pass
    if len(candidate) > 253 or candidate.endswith("."):
        return False
    label_pattern = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
    return all(label_pattern.fullmatch(label) for label in candidate.split("."))


def _is_local_host(host: object) -> bool:
    candidate = str(host).casefold()
    if (
        candidate == "testserver"
        or candidate == "localhost"
        or candidate.endswith(".localhost")
    ):
        return True
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


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
