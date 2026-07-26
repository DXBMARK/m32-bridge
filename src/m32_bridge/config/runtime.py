"""Runtime endpoint configuration resolution for local setup diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

DEFAULT_CONSOLE_PORT = 10023
VALID_TARGET_TYPES = {"emulator", "hardware", "unknown"}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error_code: str | None = None
    message: str = ""


@dataclass(frozen=True)
class RuntimeConfig:
    host: str | None = None
    port: int | None = None
    label: str | None = None
    environment: str | None = None
    intended_target_type: str = "unknown"
    config_path: Path | None = None
    config_scope: str = "user"
    source_by_field: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.intended_target_type not in VALID_TARGET_TYPES:
            raise ValueError(f"invalid intended_target_type: {self.intended_target_type}")
        if self.host and self.port is None:
            object.__setattr__(self, "port", DEFAULT_CONSOLE_PORT)
            sources = dict(self.source_by_field)
            sources.setdefault("port", "default")
            object.__setattr__(self, "source_by_field", sources)


@dataclass(frozen=True)
class ConfigResolution:
    effective_host: str | None
    effective_port: int | None
    source_by_field: dict[str, str]
    cli_args_present: bool
    env_overrides_present: bool
    user_config_present: bool
    project_local_config_present: bool
    project_local_config_used: bool = False
    error_code: str | None = None
    message: str = ""
    default_scan_attempted: bool = False
    guessed_host: str | None = None


def default_user_config_path() -> Path:
    return Path.home() / ".m32-bridge" / "runtime.yaml"


def default_project_config_path() -> Path:
    return Path(".m32-bridge") / "runtime.local.yaml"


def validate_runtime_config(config: Mapping[str, Any]) -> ValidationResult:
    target_type = str(config.get("intended_target_type", "unknown"))
    if target_type not in VALID_TARGET_TYPES:
        return ValidationResult(
            ok=False,
            error_code="INVALID_CONFIG",
            message=f"invalid intended_target_type: {target_type}",
        )
    port = config.get("port")
    if port is not None and _int_or_none(port) is None:
        return ValidationResult(ok=False, error_code="INVALID_PORT", message="invalid port")
    return ValidationResult(ok=True)


def resolve_runtime_config(
    *,
    cli_args: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    user_config_path: Path | None = None,
    project_config_path: Path | None = None,
    allow_project_local: bool = False,
) -> ConfigResolution:
    cli = dict(cli_args or {})
    env = dict(environ or {})
    user_path = user_config_path or default_user_config_path()
    project_path = project_config_path or default_project_config_path()
    user_config = _load_config_file(user_path)
    project_config = _load_config_file(project_path)

    host: str | None = None
    port: int | None = None
    source_by_field: dict[str, str] = {}

    if allow_project_local and project_config:
        host = _config_host(project_config)
        port = _config_port(project_config)
        if host:
            source_by_field["host"] = "project_local_dev_test"
        if port is not None:
            source_by_field["port"] = "project_local_dev_test"

    if user_config:
        user_host = _config_host(user_config)
        user_port = _config_port(user_config)
        if user_host:
            host = user_host
            source_by_field["host"] = "user_config"
        if user_port is not None:
            port = user_port
            source_by_field["port"] = "user_config"

    env_host = _string_or_none(env.get("M32_CONSOLE_HOST"))
    env_port = _int_or_none(env.get("M32_CONSOLE_PORT"))
    if env_host:
        host = env_host
        source_by_field["host"] = "env"
    if env_port is not None:
        port = env_port
        source_by_field["port"] = "env"

    cli_host = _string_or_none(cli.get("host"))
    cli_port = _int_or_none(cli.get("port"))
    if cli_host:
        host = cli_host
        source_by_field["host"] = "cli"
    if cli_port is not None:
        port = cli_port
        source_by_field["port"] = "cli"

    if host and port is None:
        port = DEFAULT_CONSOLE_PORT
        source_by_field.setdefault("port", "default")

    missing_host = not host
    return ConfigResolution(
        effective_host=host,
        effective_port=port if not missing_host else None,
        source_by_field=source_by_field,
        cli_args_present=bool(cli),
        env_overrides_present=bool(env_host or env.get("M32_CONSOLE_PORT")),
        user_config_present=user_path.exists(),
        project_local_config_present=project_path.exists(),
        project_local_config_used=bool(allow_project_local and project_config and source_by_field.get("host") == "project_local_dev_test"),
        error_code="NO_CONSOLE_HOST" if missing_host else None,
        message="No console host is configured. Run m32-bridge setup." if missing_host else "",
    )


def no_console_host_output(resolution: ConfigResolution) -> dict[str, Any]:
    from m32_bridge.diagnostics.runtime_output import runtime_output

    return runtime_output(
        ok=False,
        status="NO_CONSOLE_HOST",
        error_code="NO_CONSOLE_HOST",
        message=resolution.message or "No console host is configured. Run m32-bridge setup.",
        configured_host=None,
        configured_port=None,
        attempted_path="/info",
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        data={},
        recommendations=["Run m32-bridge setup", "Run m32-bridge config show"],
    )


def save_runtime_config(
    *,
    path: Path,
    host: str,
    port: int,
    intended_target_type: str,
    label: str | None = None,
    environment: str | None = None,
    config_scope: str = "user",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1",
        "host": host,
        "port": port,
        "intended_target_type": intended_target_type,
        "config_scope": config_scope,
    }
    if label:
        payload["label"] = label
    if environment:
        payload["environment"] = environment
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


def scan_for_console_hosts(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def probe_info(*_args: Any, **_kwargs: Any) -> None:
    return None


def _load_config_file(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _config_host(config: Mapping[str, Any]) -> str | None:
    return _string_or_none(config.get("host")) or _string_or_none(_target(config).get("osc_host"))


def _config_port(config: Mapping[str, Any]) -> int | None:
    return _int_or_none(config.get("port")) or _int_or_none(_target(config).get("osc_port"))


def _target(config: Mapping[str, Any]) -> Mapping[str, Any]:
    target = config.get("target")
    return target if isinstance(target, Mapping) else {}


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
