"""Runtime endpoint configuration resolution for local setup diagnostics."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONSOLE_PORT = 10023
VALID_TARGET_TYPES = {"emulator", "hardware", "unknown"}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error_code: str | None = None
    message: str = ""


@dataclass(frozen=True)
class ConfigFileLoadResult:
    values: dict[str, Any]
    present: bool
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
    effective_label: str | None = None
    effective_environment: str | None = None
    effective_intended_target_type: str = "unknown"
    config_path: Path | None = None


def default_user_config_path() -> Path:
    return Path.home() / ".m32-bridge" / "runtime.yaml"


def default_project_config_path() -> Path:
    return Path(".m32-bridge") / "runtime.local.yaml"


def validate_runtime_config(config: Mapping[str, Any]) -> ValidationResult:
    target = _target(config)
    host = config.get("host") if "host" in config else target.get("osc_host")
    if host is not None and not isinstance(host, str):
        return ValidationResult(ok=False, error_code="INVALID_HOST", message="host must be a string")

    target_type = str(config.get("intended_target_type", "unknown"))
    if target_type not in VALID_TARGET_TYPES:
        return ValidationResult(
            ok=False,
            error_code="INVALID_CONFIG",
            message=f"invalid intended_target_type: {target_type}",
        )
    port = config.get("port") if "port" in config else target.get("osc_port")
    normalized_port = _int_or_none(port)
    if port is not None and (normalized_port is None or not 1 <= normalized_port <= 65535):
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
    user_load = _load_config_file(user_path)
    project_load = _load_config_file(project_path)
    user_config = user_load.values
    project_config = project_load.values

    invalid_load = user_load if user_load.error_code else (project_load if allow_project_local and project_load.error_code else None)
    if invalid_load is not None:
        invalid_path = user_path if user_load.error_code else project_path
        return ConfigResolution(
            effective_host=None,
            effective_port=None,
            source_by_field={},
            cli_args_present=bool(cli),
            env_overrides_present=bool(env.get("M32_CONSOLE_HOST") or env.get("M32_CONSOLE_PORT")),
            user_config_present=user_load.present,
            project_local_config_present=project_load.present,
            error_code="CONFIG_INVALID",
            message=invalid_load.message or "Runtime config file is malformed.",
            config_path=invalid_path,
        )

    host: str | None = None
    port: int | None = None
    label: str | None = None
    environment: str | None = None
    intended_target_type = "unknown"
    config_path: Path | None = None
    source_by_field: dict[str, str] = {}
    validation_error: ValidationResult | None = None

    if allow_project_local and project_config:
        project_validation = validate_runtime_config(project_config)
        if not project_validation.ok:
            validation_error = project_validation
        host = _config_host(project_config)
        port = _config_port(project_config)
        label = _string_or_none(project_config.get("label"))
        environment = _string_or_none(project_config.get("environment"))
        project_has_target_type = "intended_target_type" in project_config
        intended_target_type = _target_type_or_unknown(project_config.get("intended_target_type"))
        config_path = project_path
        if host:
            source_by_field["host"] = "project_local_dev_test"
        if port is not None:
            source_by_field["port"] = "project_local_dev_test"
        if label:
            source_by_field["label"] = "project_local_dev_test"
        if project_has_target_type:
            source_by_field["intended_target_type"] = "project_local_dev_test"

    if user_config:
        user_validation = validate_runtime_config(user_config)
        if not user_validation.ok:
            validation_error = user_validation
        user_host = _config_host(user_config)
        user_port = _config_port(user_config)
        user_label = _string_or_none(user_config.get("label"))
        user_environment = _string_or_none(user_config.get("environment"))
        user_has_target_type = "intended_target_type" in user_config
        user_target_type = _target_type_or_unknown(user_config.get("intended_target_type"))
        config_path = user_path
        if user_host:
            host = user_host
            source_by_field["host"] = "user_config"
        if user_port is not None:
            port = user_port
            source_by_field["port"] = "user_config"
        if user_label is not None:
            label = user_label
            source_by_field["label"] = "user_config"
        if user_environment is not None:
            environment = user_environment
            source_by_field["environment"] = "user_config"
        if user_has_target_type:
            intended_target_type = user_target_type
            source_by_field["intended_target_type"] = "user_config"

    env_config: dict[str, Any] = {}
    if "M32_CONSOLE_HOST" in env:
        env_config["host"] = env["M32_CONSOLE_HOST"]
    if "M32_CONSOLE_PORT" in env:
        env_config["port"] = env["M32_CONSOLE_PORT"]
    env_validation = validate_runtime_config(env_config)
    if not env_validation.ok:
        validation_error = env_validation
    env_host = _host_or_none(env.get("M32_CONSOLE_HOST"))
    env_port = _int_or_none(env.get("M32_CONSOLE_PORT"))
    if env_host:
        host = env_host
        source_by_field["host"] = "env"
    if env_port is not None:
        port = env_port
        source_by_field["port"] = "env"

    cli_validation = validate_runtime_config(cli)
    if not cli_validation.ok:
        validation_error = cli_validation
    cli_host = _host_or_none(cli.get("host"))
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
    effective_values_valid = validation_error is None
    return ConfigResolution(
        effective_host=host if effective_values_valid else None,
        effective_port=port if effective_values_valid and not missing_host else None,
        source_by_field=source_by_field,
        cli_args_present=bool(cli),
        env_overrides_present=bool(env_host or env.get("M32_CONSOLE_PORT")),
        user_config_present=user_load.present,
        project_local_config_present=project_load.present,
        project_local_config_used=bool(allow_project_local and project_config and source_by_field.get("host") == "project_local_dev_test"),
        error_code=(validation_error.error_code if validation_error else ("NO_CONSOLE_HOST" if missing_host else None)),
        message=(
            validation_error.message
            if validation_error
            else ("No console host is configured. Run m32-bridge setup." if missing_host else "")
        ),
        effective_label=label,
        effective_environment=environment,
        effective_intended_target_type=intended_target_type,
        config_path=config_path,
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
    yaml = _yaml_module()
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
    serialized = yaml.safe_dump(payload, sort_keys=True)
    temp_name: str | None = None
    fd: int | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def scan_for_console_hosts(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def probe_info(*_args: Any, **_kwargs: Any) -> None:
    return None


def _load_config_file(path: Path) -> ConfigFileLoadResult:
    if not path.exists():
        return ConfigFileLoadResult(values={}, present=False)
    yaml = _yaml_module()
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return ConfigFileLoadResult(values={}, present=True)
    except yaml.YAMLError:
        return ConfigFileLoadResult(
            values={},
            present=True,
            error_code="CONFIG_INVALID",
            message="Runtime config file is malformed.",
        )
    if loaded is None:
        return ConfigFileLoadResult(values={}, present=True)
    if not isinstance(loaded, dict):
        return ConfigFileLoadResult(
            values={},
            present=True,
            error_code="CONFIG_INVALID",
            message="Runtime config file must contain a mapping.",
        )
    return ConfigFileLoadResult(values=loaded, present=True)


def _yaml_module() -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyYAML is required to read or write runtime configuration. "
            "Complete the managed application installation, then retry."
        ) from exc
    return yaml


def _config_host(config: Mapping[str, Any]) -> str | None:
    return _host_or_none(config.get("host")) or _host_or_none(_target(config).get("osc_host"))


def _config_port(config: Mapping[str, Any]) -> int | None:
    value = config.get("port") if "port" in config else _target(config).get("osc_port")
    return _int_or_none(value)


def _target(config: Mapping[str, Any]) -> Mapping[str, Any]:
    target = config.get("target")
    return target if isinstance(target, Mapping) else {}


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _host_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _target_type_or_unknown(value: object) -> str:
    text = _string_or_none(value) or "unknown"
    return text if text in VALID_TARGET_TYPES else "unknown"
