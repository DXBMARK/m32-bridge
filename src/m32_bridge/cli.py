"""Local operator controls for the M32 bridge."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from jsonschema import ValidationError

from m32_bridge.config.runtime import (
    VALID_TARGET_TYPES,
    default_project_config_path,
    default_user_config_path,
    no_console_host_output,
    resolve_runtime_config,
    save_runtime_config,
    validate_runtime_config,
)
from m32_bridge.config.schemas import validate_with_schema
from m32_bridge.diagnostics.os_recommendations import build_os_recommendations
from m32_bridge.diagnostics.runtime_output import runtime_output
from m32_bridge.runtime_preconditions import evaluate_console_precondition

DEFAULT_REQUIRED_PATHS = ("/ch/01/headamp/gain", "/rta/source")


def setup_info_probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from m32_bridge.diagnostics.runtime import setup_info_probe as probe

    return probe(*args, **kwargs)


def health() -> dict[str, Any]:
    from m32_bridge.installer.runtime_status import build_runtime_health

    runtime_environ = dict(os.environ)
    result = build_runtime_health(
        {
            "app_path": runtime_environ.get("M32_BRIDGE_APP_DIR"),
            "launcher_path": runtime_environ.get("M32_BRIDGE_LAUNCHER"),
        },
        environ=runtime_environ,
    )
    invalid = result["configuration_state"] == "invalid"
    configured = result["configuration_state"] == "valid"
    result.update(_base_result("health", "CONFIG_INVALID" if invalid else result["status"]))
    result["ok"] = bool(result["application_health"] == "healthy" and not invalid)
    if invalid:
        result["error_code"] = "CONFIG_INVALID"
    result["checks"] = {
        "cli": "ok",
        "runtime": result["application"],
        "config": "invalid" if invalid else ("present" if configured else "not_configured"),
        "launcher": result["application"].get("launcher_executable"),
        "console_probe": "not_run",
        "network_scan": "not_run",
        "osc_writes_sent": 0,
        "mcp_primary_transport": "stdio",
        "webui": "absent",
        "production_live_ready": False,
    }
    result.update(
        {
            "application_runtime": result["application_health"],
            "managed_python": result["application"]["managed_python"],
            "frozen_launcher": "enabled",
            "console_configured": configured,
            "console_connection": result["connection_state"],
            "operational_readiness": result["operational_state"],
            "next_action": result["configuration_readiness"]["next_action"],
            "precondition_state": "config_invalid" if invalid else ("ready" if configured else "setup_required"),
            "required_action": None if configured else "m32-bridge setup",
            "attempted_path": "not_attempted",
            "console_probe": "not_run",
            "network_scan": "not_run",
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }
    )
    return result


def doctor(*, config_path: Path = Path("config.example.yaml")) -> dict[str, Any]:
    import yaml

    result = _base_result("doctor", "ok")
    checks: dict[str, Any] = {
        "config_schema": {"status": "not_checked", "path": str(config_path)},
        "runtime_status": {"write_locked_on_startup": None},
        "secondary_transport": {"status": "unknown"},
        "operator_controls": {"status": "ok", "read_only": True},
    }
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        validate_with_schema(config, "config.schema.json")
    except (OSError, ValidationError, yaml.YAMLError) as exc:
        result["status"] = "error"
        checks["config_schema"] = {"status": "error", "path": str(config_path), "error": exc.__class__.__name__}
    else:
        streamable = config.get("transports", {}).get("streamable_http", {}) if isinstance(config, dict) else {}
        checks["config_schema"] = {"status": "ok", "path": str(config_path)}
        checks["runtime_status"] = {
            "default_mode": config.get("runtime", {}).get("default_mode"),
            "write_locked_on_startup": config.get("runtime", {}).get("write_locked_on_startup"),
        }
        checks["secondary_transport"] = {"status": "enabled" if streamable.get("enabled") else "disabled"}
    result["checks"] = checks
    result["hardware_verified"] = False
    return result


def operator_snapshot(client: OscClient, *, snapshot_id: str | None = None) -> dict[str, Any]:
    from m32_bridge.osc.discovery import discover_identity
    from m32_bridge.state.snapshot import build_snapshot

    discovery = discover_identity(client.transport)
    state_values = [_state_value_dict(client, path) for path in DEFAULT_REQUIRED_PATHS]
    identity = discovery.identity.__dict__.copy()
    identity["observed_at"] = identity["observed_at"].isoformat()
    identity["verification_state"] = identity["verification_state"].value
    snapshot = build_snapshot(
        snapshot_id=snapshot_id or f"snap_{uuid4().hex}",
        identity=identity,
        firmware={"version": discovery.identity.firmware_version, "status": discovery.identity.firmware_status},
        state_values=state_values,
        environment_label=discovery.identity.environment_label,
    )
    snapshot["hardware_verified"] = False
    result = _base_result("snapshot", "ok")
    result["snapshot"] = snapshot
    result["hardware_verified"] = False
    result["read_only_checks"] = ["/info", *DEFAULT_REQUIRED_PATHS]
    return result


def verify_connection(client: OscClient) -> dict[str, Any]:
    from m32_bridge.core.connection import ConnectionController

    controller = ConnectionController(client, required_paths=DEFAULT_REQUIRED_PATHS)
    reconciliation = controller.reconcile_after_reconnect()
    result = _base_result("verify-connection", "ok" if reconciliation.reconciled else "error")
    result["connection"] = {
        "status": reconciliation.status,
        "write_locked": reconciliation.write_locked,
        "reconciled": reconciliation.reconciled,
        "reason": reconciliation.reason,
        "identity": controller.identity,
    }
    result["hardware_verified"] = False
    result["read_only_checks"] = ["/info", *DEFAULT_REQUIRED_PATHS]
    return result


def audit_tail(audit_path: Path, *, limit: int = 20) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if audit_path.exists():
        lines = audit_path.read_text(encoding="utf-8").splitlines()
        for line in lines[-max(0, limit) :]:
            if line.strip():
                records.append(json.loads(line))
    result = _base_result("audit-tail", "ok")
    result["audit_path"] = str(audit_path)
    result["records"] = records
    result["records_returned"] = len(records)
    return result


def setup_runtime(
    *,
    host: str | None,
    port: int | None,
    target_type: str,
    label: str | None = None,
    environment: str | None = None,
    save: bool = False,
    confirm_save: bool = False,
    config_path: Path | None = None,
    config_scope: str = "user",
    timeout: float = 0.5,
    probe_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if host is not None and not str(host).strip():
        return runtime_output(
            ok=False,
            status="INVALID_HOST",
            error_code="INVALID_HOST",
            message="Host must be a non-empty configured address.",
            configured_host=None,
            configured_port=port if port and 1 <= port <= 65535 else None,
            attempted_path="/info",
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
    if host is None:
        resolution = resolve_runtime_config(cli_args={}, environ={}, allow_project_local=False)
        return no_console_host_output(resolution)
    if port is None:
        port = 10023
    if port is None or port < 1 or port > 65535:
        return runtime_output(
            ok=False,
            status="INVALID_PORT",
            error_code="INVALID_PORT",
            message="Port must be between 1 and 65535.",
            configured_host=str(host).strip(),
            configured_port=None,
            attempted_path="/info",
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
    if target_type not in VALID_TARGET_TYPES:
        return runtime_output(
            ok=False,
            status="INVALID_CONFIG",
            error_code="INVALID_CONFIG",
            message=f"Invalid target type: {target_type}",
            configured_host=str(host).strip(),
            configured_port=port,
            attempted_path="/info",
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
                production_live_ready=False,
        )

    saved = False
    persistence_verified = False
    resolved_config_path = config_path or (default_project_config_path() if config_scope == "project_dev_test" else default_user_config_path())
    if save and confirm_save:
        try:
            save_runtime_config(
                path=resolved_config_path,
                host=str(host).strip(),
                port=port,
                intended_target_type=target_type,
                label=label,
                environment=environment,
                config_scope=config_scope,
            )
        except OSError as exc:
            payload = runtime_output(
                ok=False,
                status="CONFIG_WRITE_FAILED",
                error_code="CONFIG_WRITE_FAILED",
                message="Runtime configuration could not be saved.",
                configured_host=str(host).strip(),
                configured_port=port,
                attempted_path=None,
                latency_ms=None,
                exception_type=type(exc).__name__,
                connected=False,
                osc_writes_sent=0,
                hardware_verified=False,
                production_live_ready=False,
            )
            payload.update(
                {
                    "saved": False,
                    "config_saved": False,
                    "config_path": str(resolved_config_path),
                    "persistence_verified": False,
                    "probe_attempted": False,
                    "endpoint_verified": False,
                    "config_not_written": True,
                    "scan_attempted": False,
                }
            )
            return payload
        saved = True
        resolved = resolve_runtime_config(
            cli_args={},
            environ={},
            user_config_path=resolved_config_path,
            allow_project_local=False,
        )
        persistence_verified = bool(
            resolved.effective_host == str(host).strip()
            and resolved.effective_port == port
            and resolved.effective_intended_target_type == target_type
            and (label is None or resolved.effective_label == label)
        )

    probe = probe_result or setup_info_probe(str(host).strip(), port, timeout=timeout)
    response_address = probe.get("response_address")
    connected = probe.get("udp_info_probe_result") == "CONNECTED"
    latency_ms = probe.get("latency_ms")
    exception_type = probe.get("exception_type")

    if connected and response_address is not None and _response_address_mismatch(response_address, str(host).strip(), port):
        payload = runtime_output(
            ok=bool(saved),
            status="SAVED_UNEXPECTED_RESPONSE_ADDRESS" if saved else "UNEXPECTED_RESPONSE_ADDRESS",
            error_code=None if saved else "UNEXPECTED_RESPONSE_ADDRESS",
            message="Configuration was saved, but the /info response came from an unexpected address." if saved else "The /info response came from an unexpected address.",
            configured_host=str(host).strip(),
            configured_port=port,
            attempted_path="/info",
            latency_ms=latency_ms,
            exception_type=exception_type,
            response_address=response_address,
            connected=True,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
        payload.update(
            {
                "saved": saved,
                "config_saved": saved,
                "config_path": str(resolved_config_path),
                "persistence_verified": persistence_verified,
                "probe_attempted": True,
                "endpoint_verified": False,
                "scan_attempted": False,
            }
        )
        return payload

    if not connected:
        error_code = "CONNECT_TIMEOUT" if exception_type and "Timeout" in str(exception_type) else "NOT_CONNECTED"
        payload = runtime_output(
            ok=bool(saved),
            status="SAVED_NOT_CONNECTED" if saved else "NOT_CONNECTED",
            error_code=None if saved else error_code,
            message="Configuration was saved successfully. The endpoint is currently unavailable or did not respond." if saved else "The configured endpoint did not respond to /info.",
            configured_host=str(host).strip(),
            configured_port=port,
            attempted_path="/info",
            latency_ms=latency_ms,
            exception_type=exception_type,
            response_address=response_address,
            connected=False,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
        payload.update(
            {
                "saved": saved,
                "config_saved": saved,
                "config_path": str(resolved_config_path),
                "persistence_verified": persistence_verified,
                "probe_attempted": True,
                "endpoint_verified": False,
                "verification_status": error_code,
                "scan_attempted": False,
            }
        )
        return payload

    payload = runtime_output(
        ok=True,
        status="CONNECTED" if saved else "NOT_SAVED",
        error_code=None,
        message="Setup probe connected.",
        configured_host=str(host).strip(),
        configured_port=port,
        attempted_path="/info",
        latency_ms=latency_ms,
        exception_type=exception_type,
        response_address=response_address,
        connected=True,
        classification="EMULATOR_CONNECTED" if target_type == "emulator" else "CONNECTED_UNVERIFIED",
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        data={"target_type": target_type, "os_recommendations": _current_os_recommendations()},
        recommendations=["Run m32-bridge mcp-server after saving config."],
    )
    payload["saved"] = saved
    payload["config_saved"] = saved
    payload["config_path"] = str(resolved_config_path)
    payload["persistence_verified"] = persistence_verified if saved else False
    payload["probe_attempted"] = True
    payload["endpoint_verified"] = True
    payload["scan_attempted"] = False
    return payload


def detect_device_runtime(
    *,
    host: str | None,
    port: int | None,
    target_type: str,
    timeout: float = 0.5,
    probe_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from m32_bridge.diagnostics.device_identity import classify_device

    if host is None:
        resolution = resolve_runtime_config(cli_args={}, environ={}, allow_project_local=False)
        return classify_device(
            configured_host=resolution.effective_host,
            configured_port=resolution.effective_port,
            intended_target_type=target_type,
            info_probe=None,
        )
    if port is None:
        port = 10023
    probe = probe_result or setup_info_probe(str(host).strip(), port, timeout=timeout)
    probe.setdefault("attempted_path", "/info")
    probe.setdefault("configured_host", str(host).strip())
    probe.setdefault("configured_port", port)
    probe.setdefault("connected", probe.get("udp_info_probe_result") == "CONNECTED")
    probe.setdefault("osc_writes_sent", 0)
    payload = classify_device(
        configured_host=str(host).strip(),
        configured_port=port,
        intended_target_type=target_type,
        info_probe=probe,
    )
    payload.setdefault("data", {})["os_recommendations"] = _current_os_recommendations()
    return payload


def get_info_runtime(
    *,
    host: str | None,
    port: int | None,
    timeout: float = 0.5,
    probe_result: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    user_config_path: Path | None = None,
) -> dict[str, Any]:
    resolution = None

    if host is None:
        runtime_environ = dict(
            os.environ
            if environ is None
            else environ
        )

        resolution = resolve_runtime_config(
            cli_args=_present_cli_args(
                host=host,
                port=port,
            ),
            environ=runtime_environ,
            user_config_path=user_config_path,
            allow_project_local=False,
        )

        if not resolution.effective_host:
            payload = no_console_host_output(resolution)
            payload["scan_attempted"] = False
            payload["network_scan"] = "not_run"
            payload["guessed_host"] = None
            payload["source_by_field"] = dict(
                resolution.source_by_field
            )
            payload["config_path"] = (
                str(resolution.config_path)
                if resolution.config_path
                else None
            )
            return payload

        host = resolution.effective_host
        port = resolution.effective_port

    if port is None:
        port = 10023
    probe = probe_result or setup_info_probe(str(host).strip(), port, timeout=timeout)
    connected = probe.get("udp_info_probe_result") == "CONNECTED"
    info_raw = list(probe.get("info_raw") or [])
    info_data = {
        "info_raw": probe.get("info_raw"),
        "model": str(info_raw[0]) if len(info_raw) >= 1 else None,
        "firmware": str(info_raw[1]) if len(info_raw) >= 2 else None,
        "api_version": str(info_raw[2]) if len(info_raw) >= 3 else None,
        "name": str(info_raw[3]) if len(info_raw) >= 4 else None,
        "host": str(host).strip(),
        "port": port,
        "latency_ms": probe.get("latency_ms"),
        "classification": "CONNECTED_UNVERIFIED" if connected else "unknown",
    }
    payload = runtime_output(
        ok=bool(connected),
        status="CONNECTED" if connected else "NOT_CONNECTED",
        error_code=None if connected else "NOT_CONNECTED",
        message="Read /info from configured endpoint." if connected else "The configured endpoint did not respond to /info.",
        configured_host=str(host).strip(),
        configured_port=port,
        attempted_path="/info",
        latency_ms=probe.get("latency_ms"),
        exception_type=probe.get("exception_type"),
        response_address=probe.get("response_address"),
        connected=connected,
        classification="CONNECTED_UNVERIFIED" if connected else "unknown",
        data=info_data,
        recommendations=["Run m32-bridge setup if this endpoint is not the intended console."],
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
    )
    payload["scan_attempted"] = False
    payload["network_scan"] = "not_run"

    if resolution is not None:
        payload["source_by_field"] = dict(
            resolution.source_by_field
        )
        payload["config_path"] = (
            str(resolution.config_path)
            if resolution.config_path
            else None
        )

    return payload


def doctor_runtime_command(
    *,
    host: str | None,
    port: int | None,
    timeout: float,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    from m32_bridge.installer.runtime_manager import local_runtime_diagnostics

    payload = local_runtime_diagnostics(environ=environ)
    payload.update(
        {
            "control": "doctor-runtime",
            "configured_host": host,
            "configured_port": port,
            "requested_timeout": timeout,
            "attempted_path": None,
            "console_probe": "not_run",
            "connection_lifecycle": "not_checked",
            "structured": True,
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }
    )
    payload["os_recommendations"] = _current_os_recommendations()
    return payload


def config_show_runtime(*, config_path: Path) -> dict[str, Any]:
    resolution = resolve_runtime_config(
        cli_args={},
        environ={},
        user_config_path=config_path,
        allow_project_local=False,
    )
    if resolution.error_code and resolution.error_code != "NO_CONSOLE_HOST":
        error_code = "CONFIG_INVALID" if resolution.error_code in {"CONFIG_INVALID", "INVALID_CONFIG"} else resolution.error_code
        payload = runtime_output(
            ok=False,
            status=error_code,
            error_code=error_code,
            message=resolution.message or "Runtime config is invalid.",
            configured_host=None,
            configured_port=None,
            attempted_path="not_attempted",
            latency_ms=None,
            exception_type="ConfigurationError",
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
        payload.update(
            config_path=str(resolution.config_path or config_path),
            console_probe="not_run",
            network_scan="not_run",
        )
        return payload
    if resolution.error_code == "NO_CONSOLE_HOST":
        payload = no_console_host_output(resolution)
        payload["config_path"] = str(config_path)
        return payload

    raw_config = _load_runtime_config_strict(config_path)

    payload = runtime_output(
        ok=True,
        status="CONFIGURED",
        error_code=None,
        message="Runtime config is configured.",
        configured_host=resolution.effective_host,
        configured_port=resolution.effective_port,
        attempted_path=None,
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        data=_non_secret_config(raw_config),
        recommendations=["Use m32-bridge mcp-server from a local MCP host."],
    )
    payload["config_path"] = str(config_path)
    payload["source_by_field"] = resolution.source_by_field
    payload["config_resolution"] = _config_resolution_dict(resolution)
    return payload


def config_validate_runtime(
    *,
    host: str | None,
    port: int | None,
    config_path: Path,
    project_config_path: Path | None = None,
    allow_project_local: bool = False,
) -> dict[str, Any]:
    if host is not None and not str(host).strip():
        return runtime_output(
            ok=False,
            status="INVALID_HOST",
            error_code="INVALID_HOST",
            message="Host must be a non-empty configured address.",
            configured_host=None,
            configured_port=port if port and 1 <= port <= 65535 else None,
            attempted_path=None,
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
    if port is not None and (port < 1 or port > 65535):
        return runtime_output(
            ok=False,
            status="INVALID_PORT",
            error_code="INVALID_PORT",
            message="Port must be between 1 and 65535.",
            configured_host=str(host).strip() if host else None,
            configured_port=None,
            attempted_path=None,
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )

    resolution = resolve_runtime_config(
        cli_args=_present_cli_args(host=host, port=port),
        environ=os.environ,
        user_config_path=config_path,
        project_config_path=project_config_path,
        allow_project_local=allow_project_local,
    )
    if resolution.error_code and resolution.error_code != "NO_CONSOLE_HOST":
        return runtime_output(
            ok=False,
            status=resolution.error_code,
            error_code=resolution.error_code,
            message=resolution.message or "Runtime config is invalid.",
            configured_host=resolution.effective_host,
            configured_port=None if resolution.error_code == "INVALID_PORT" else resolution.effective_port,
            attempted_path=None,
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
    if resolution.error_code == "NO_CONSOLE_HOST":
        payload = no_console_host_output(resolution)
        payload["config_path"] = str(config_path)
        payload["config_resolution"] = _config_resolution_dict(resolution)
        return payload

    validation = validate_runtime_config({"host": resolution.effective_host, "port": resolution.effective_port})
    if not validation.ok:
        return runtime_output(
            ok=False,
            status=validation.error_code or "INVALID_CONFIG",
            error_code=validation.error_code or "INVALID_CONFIG",
            message=validation.message,
            configured_host=resolution.effective_host,
            configured_port=None if validation.error_code == "INVALID_PORT" else resolution.effective_port,
            attempted_path=None,
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )

    payload = runtime_output(
        ok=True,
        status="VALID",
        error_code=None,
        message="Runtime config is valid.",
        configured_host=resolution.effective_host,
        configured_port=resolution.effective_port,
        attempted_path=None,
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        recommendations=["Use m32-bridge config show to inspect active values."],
    )
    payload["config_path"] = str(config_path)
    payload["source_by_field"] = resolution.source_by_field
    payload["config_resolution"] = _config_resolution_dict(resolution)
    return payload


def config_set_runtime(*, host: str | None, port: int | None, config_path: Path) -> dict[str, Any]:
    if host is not None and not str(host).strip():
        return runtime_output(
            ok=False,
            status="INVALID_HOST",
            error_code="INVALID_HOST",
            message="Host must be a non-empty configured address.",
            configured_host=None,
            configured_port=port if port and 1 <= port <= 65535 else None,
            attempted_path=None,
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
    if port is not None and (port < 1 or port > 65535):
        return runtime_output(
            ok=False,
            status="INVALID_PORT",
            error_code="INVALID_PORT",
            message="Port must be between 1 and 65535.",
            configured_host=str(host).strip() if host else None,
            configured_port=None,
            attempted_path=None,
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )

    existing = _load_runtime_config_strict(config_path)
    resolved_host = str(host).strip() if host is not None else _config_value_host(existing)
    resolved_port = port if port is not None else _config_value_port(existing)
    if resolved_host is None:
        resolution = resolve_runtime_config(cli_args={}, environ={}, user_config_path=config_path)
        payload = no_console_host_output(resolution)
        payload["config_path"] = str(config_path)
        return payload
    if resolved_port is None:
        resolved_port = 10023

    save_runtime_config(
        path=config_path,
        host=resolved_host,
        port=resolved_port,
        intended_target_type=str(existing.get("intended_target_type", "unknown")),
        label=existing.get("label") if isinstance(existing.get("label"), str) else None,
        environment=existing.get("environment") if isinstance(existing.get("environment"), str) else None,
        config_scope=str(existing.get("config_scope", "user")),
    )
    payload = runtime_output(
        ok=True,
        status="SAVED",
        error_code=None,
        message="Runtime config saved.",
        configured_host=resolved_host,
        configured_port=resolved_port,
        attempted_path=None,
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        recommendations=["Run m32-bridge config show to inspect saved config."],
    )
    payload["config_path"] = str(config_path)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from m32_bridge.installer.tty_app import run_runtime_tty

            return run_runtime_tty()
        result = _non_interactive_runtime_tty_output()
        print(json.dumps(result, sort_keys=True), file=sys.stdout)
        return 1
    if args.command == "run":
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            result = _non_interactive_runtime_tty_output()
            print(json.dumps(result, sort_keys=True), file=sys.stdout)
            return 1
        from m32_bridge.installer.tty_app import run_runtime_tty

        return run_runtime_tty()
    if args.command == "mcp-server":
        from m32_bridge.mcp.server import run_mcp_stdio_server

        return run_mcp_stdio_server()
    try:
        result = _run_command(args)
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        print(json.dumps(_base_result(args.command, "error") | {"error": exc.__class__.__name__}), file=sys.stdout)
        return 1

    if args.command == "mcp-config" and not args.json:
        print(_render_mcp_config_cli_text(result), file=sys.stdout)
    elif args.command == "status" and not args.json:
        print(_render_status_cli_text(result), file=sys.stdout)
    else:
        print(json.dumps(result, sort_keys=True), file=sys.stdout)
    return 0 if result.get("ok") is True or result.get("status") == "ok" else 1


def _render_mcp_config_cli_text(payload: dict[str, Any]) -> str:
    lines = [
        "MCP CLIENT SETUP",
        "=" * 60,
        f"Product               : {payload['product']}",
        f"Version               : {payload['version']}",
        f"Launcher              : {payload['launcher_path']}",
        f"Runtime configuration : {payload['runtime_config_path']}",
        f"Transport             : {payload['transport']}",
        f"Environment variables : {payload['environment_variables']}",
    ]
    for profile in payload.get("client_guidance", []):
        lines.extend(
            [
                "",
                str(profile["display_name"]).upper(),
                "-" * 60,
                f"Display name         : {profile['display_name']}",
                f"Server name          : {payload['server_name']}",
                f"Command              : {profile['command'] or 'not available'}",
                f"Arguments            : {json.dumps(profile['args'])}",
                f"Environment          : {json.dumps(profile['environment'], sort_keys=True) if profile['environment'] else 'none required'}",
                f"Transport            : {profile['transport']}",
                f"Config location hint : {profile['config_location_hint']}",
            ]
        )
        if profile.get("generated_snippet") is not None:
            lines.extend(["Generated snippet:", *json.dumps(profile["generated_snippet"], indent=2).splitlines()])
        lines.append("Verification steps:")
        lines.extend(f"  - {step}" for step in profile.get("verification_steps", []))
        lines.append("Warnings / limitations:")
        lines.extend(f"  - {note}" for note in profile.get("notes", []))
        lines.append(f"  - {profile['official_support_status']}")
    lines.extend(
        [
            "",
            "SAFETY",
            "-" * 60,
            f"Client config write : {str(payload['config_written']).lower()}",
            f"Network scan        : {str(payload['network_scan']).lower()}",
            f"Console probe       : {payload['console_probe']}",
            f"OSC writes          : {payload['osc_writes_sent']}",
        ]
    )
    return "\n".join(lines)


def _render_status_cli_text(payload: dict[str, Any]) -> str:
    lines = ["RUNTIME STATUS", "=" * 60]
    for section_name, key in (
        ("APPLICATION", "application"),
        ("PLATFORM", "platform"),
        ("PYTHON RUNTIME", "python_runtime"),
        ("INSTALLATION SOURCE", "installation_source"),
        ("SOURCE CONNECTIVITY", "source_connectivity"),
        ("CONSOLE CONFIGURATION", "console_configuration"),
        ("CONSOLE CONNECTION", "console_connection"),
        ("SAFETY", "safety"),
    ):
        lines.extend(["", section_name, "-" * 60])
        values = payload.get(key) if isinstance(payload.get(key), dict) else {}
        for field, value in values.items():
            lines.append(f"{field.replace('_', ' ').title():28}: {str(value).lower() if isinstance(value, bool) else value}")
    return "\n".join(lines)


def _run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "health":
        return health()
    if args.command == "status":
        from m32_bridge.installer.runtime_status import build_runtime_status

        return build_runtime_status(
            {
                "app_path": os.environ.get("M32_BRIDGE_APP_DIR"),
                "launcher_path": os.environ.get("M32_BRIDGE_LAUNCHER"),
            },
            environ=dict(os.environ),
            refresh=bool(args.refresh),
        )
    if args.command == "doctor":
        return doctor(config_path=args.config)
    if args.command == "doctor-runtime":
        return doctor_runtime_command(host=args.host, port=args.port, timeout=args.timeout)
    if args.command == "setup":
        from m32_bridge.installer.first_run import run_setup_probe

        if args.host is None:
            from m32_bridge.installer.first_run import interactive_wizard, non_tty_setup_response

            if sys.stdin.isatty() and sys.stdout.isatty() and not args.json:
                return interactive_wizard()
            return non_tty_setup_response(environ=dict(os.environ))
        return run_setup_probe(
            host=args.host,
            port=args.port,
            target_type=args.target_type,
            label=args.label,
            environment=args.environment,
            confirm_save=(not args.no_save) and args.yes,
            config_path=args.config_path,
            config_scope=args.config_scope,
            timeout=args.timeout,
            environ=dict(os.environ),
        )
    if args.command == "install-status":
        from m32_bridge.installer.verification import render_post_install_verification

        return render_post_install_verification(environ=dict(os.environ), home=args.home, local_app_data=args.local_app_data)
    if args.command == "verify-install":
        from m32_bridge.installer.verification import render_post_install_verification

        payload = render_post_install_verification(environ=dict(os.environ), home=args.home, local_app_data=args.local_app_data)
        payload["status"] = "install_verified"
        return payload
    if args.command == "mcp-config":
        from m32_bridge.installer.mcp_guidance import render_mcp_guidance
        from m32_bridge.installer.tty_app import application_version

        return render_mcp_guidance(
            environ=dict(os.environ),
            client=args.client,
            version=application_version(),
        )
    if args.command == "get-info":
        if args.host is None:
            required = _console_setup_precondition()
            if required is not None:
                return required
        return get_info_runtime(host=args.host, port=args.port, timeout=args.timeout)
    if args.command == "detect-device":
        if args.host is None:
            required = _console_setup_precondition()
            if required is not None:
                return required
        return detect_device_runtime(
            host=args.host,
            port=args.port,
            target_type=args.target_type,
            timeout=args.timeout,
        )
    if args.command == "config":
        if args.config_command == "show":
            return config_show_runtime(config_path=args.config_path)
        if args.config_command == "validate":
            return config_validate_runtime(
                host=args.host,
                port=args.port,
                config_path=args.config_path,
                project_config_path=args.project_config_path,
                allow_project_local=args.allow_project_local,
            )
        if args.config_command == "set":
            return config_set_runtime(host=args.host, port=args.port, config_path=args.config_path)
    if args.command == "snapshot":
        return operator_snapshot(_client_from_args(args))
    if args.command == "verify-connection":
        return verify_connection(_client_from_args(args))
    if args.command == "audit-tail":
        return audit_tail(args.audit_path, limit=args.limit)
    raise ValueError(f"unknown command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="m32-bridge", description="Local M32 bridge operator controls")
    subparsers = parser.add_subparsers(dest="command", required=False)
    subparsers.add_parser("run", help="Open the branded Runtime Console")
    subparsers.add_parser("health")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--refresh", action="store_true")
    status_parser.add_argument("--json", action="store_true")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--config", type=Path, default=Path("config.example.yaml"))

    runtime_parser = subparsers.add_parser("doctor-runtime")
    runtime_parser.add_argument("--host", default=None)
    runtime_parser.add_argument("--port", type=int, default=None)
    runtime_parser.add_argument("--timeout", type=float, default=0.5)

    install_status_parser = subparsers.add_parser("install-status")
    install_status_parser.add_argument("--json", action="store_true")
    install_status_parser.add_argument("--home", type=Path, default=None)
    install_status_parser.add_argument("--local-app-data", type=Path, default=None)

    verify_install_parser = subparsers.add_parser("verify-install")
    verify_install_parser.add_argument("--json", action="store_true")
    verify_install_parser.add_argument("--home", type=Path, default=None)
    verify_install_parser.add_argument("--local-app-data", type=Path, default=None)

    mcp_config_parser = subparsers.add_parser("mcp-config")
    mcp_config_parser.add_argument("--client", choices=("claude", "codex", "gemini", "antigravity", "chatgpt", "generic", "all"), default="all")
    mcp_config_parser.add_argument("--json", action="store_true")

    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--host", default=None)
    setup_parser.add_argument("--port", type=int, default=None)
    setup_parser.add_argument("--target-type", choices=sorted(VALID_TARGET_TYPES), default="unknown")
    setup_parser.add_argument("--label", default=None)
    setup_parser.add_argument("--environment", default=None)
    setup_parser.add_argument("--timeout", type=float, default=0.5)
    setup_parser.add_argument("--json", action="store_true")
    setup_parser.add_argument("--no-save", action="store_true")
    setup_parser.add_argument("--yes", action="store_true")
    setup_parser.add_argument("--config-path", type=Path, default=None)
    setup_parser.add_argument("--config-scope", choices=("user", "project_dev_test"), default="user")

    get_info_parser = subparsers.add_parser("get-info")
    get_info_parser.add_argument("--host", default=None)
    get_info_parser.add_argument("--port", type=int, default=None)
    get_info_parser.add_argument("--timeout", type=float, default=0.5)
    get_info_parser.add_argument("--json", action="store_true")

    detect_parser = subparsers.add_parser("detect-device")
    detect_parser.add_argument("--host", default=None)
    detect_parser.add_argument("--port", type=int, default=None)
    detect_parser.add_argument("--target-type", choices=sorted(VALID_TARGET_TYPES), default="unknown")
    detect_parser.add_argument("--timeout", type=float, default=0.5)
    detect_parser.add_argument("--json", action="store_true")

    config_parser = subparsers.add_parser("config")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_show_parser = config_subparsers.add_parser("show")
    config_show_parser.add_argument("--config-path", type=Path, default=default_user_config_path())
    config_show_parser.add_argument("--json", action="store_true")

    config_validate_parser = config_subparsers.add_parser("validate")
    config_validate_parser.add_argument("--host", default=None)
    config_validate_parser.add_argument("--port", type=int, default=None)
    config_validate_parser.add_argument("--config-path", type=Path, default=default_user_config_path())
    config_validate_parser.add_argument("--project-config-path", type=Path, default=default_project_config_path())
    config_validate_parser.add_argument("--allow-project-local", action="store_true")
    config_validate_parser.add_argument("--json", action="store_true")

    config_set_parser = config_subparsers.add_parser("set")
    config_set_parser.add_argument("--host", default=None)
    config_set_parser.add_argument("--port", type=int, default=None)
    config_set_parser.add_argument("--config-path", type=Path, default=default_user_config_path())
    config_set_parser.add_argument("--json", action="store_true")

    snapshot_parser = subparsers.add_parser("snapshot")
    _add_client_args(snapshot_parser)

    verify_parser = subparsers.add_parser("verify-connection")
    _add_client_args(verify_parser)

    audit_parser = subparsers.add_parser("audit-tail")
    audit_parser.add_argument("--audit-path", type=Path, default=Path(".local/audit/m32-bridge.audit.jsonl"))
    audit_parser.add_argument("--limit", type=int, default=20)

    subparsers.add_parser("mcp-server")
    return parser


def _non_interactive_runtime_tty_output() -> dict[str, Any]:
    return runtime_output(
        ok=False,
        status="NON_INTERACTIVE_SHELL_REQUIRED",
        error_code="NON_INTERACTIVE_SHELL_REQUIRED",
        message="Runtime Console requires an interactive terminal. Use a one-shot command instead.",
        attempted_path="not_attempted",
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        recommendations=["m32-bridge --help", "m32-bridge health", "m32-bridge setup", "m32-bridge mcp-server"],
    ) | {"started": False, "network_scan": "not_run"}


def _console_setup_precondition() -> dict[str, Any] | None:
    precondition = evaluate_console_precondition(environ=dict(os.environ))
    if precondition.state == "ready":
        return None
    if precondition.state == "config_invalid":
        return runtime_output(
            ok=False,
            status="CONFIG_INVALID",
            error_code="CONFIG_INVALID",
            message="The saved console configuration is invalid.",
            attempted_path="not_attempted",
            latency_ms=None,
            exception_type=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
            recommendations=["m32-bridge setup"],
        ) | precondition.as_dict()
    return runtime_output(
        ok=False,
        status="SETUP_REQUIRED",
        error_code="SETUP_REQUIRED",
        message="A console endpoint has not been configured.",
        attempted_path="not_attempted",
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        recommendations=["m32-bridge setup"],
    ) | precondition.as_dict()


def _add_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=10023)
    parser.add_argument("--timeout", type=float, default=0.5)


def _client_from_args(args: argparse.Namespace) -> OscClient:
    from m32_bridge.osc.client import OscClient
    from m32_bridge.osc.transport import OscTransport

    return OscClient(OscTransport(args.host, args.port, timeout=args.timeout))


def _response_address_mismatch(response_address: object, host: str, port: int) -> bool:
    if not isinstance(response_address, (list, tuple)) or len(response_address) < 2:
        return False
    response_host = str(response_address[0])
    try:
        response_port = int(response_address[1])
    except (TypeError, ValueError):
        return True
    return response_host != host or response_port != port


def _load_runtime_config_strict(path: Path) -> dict[str, Any]:
    import yaml

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _non_secret_config(config: dict[str, Any]) -> dict[str, Any]:
    blocked = {"token", "secret", "password", "claude_desktop_config"}
    return {key: value for key, value in config.items() if key.lower() not in blocked}


def _present_cli_args(*, host: str | None, port: int | None) -> dict[str, Any]:
    args: dict[str, Any] = {}
    if host is not None:
        args["host"] = host
    if port is not None:
        args["port"] = port
    return args


def _config_resolution_dict(resolution: Any) -> dict[str, Any]:
    return {
        "effective_host": resolution.effective_host,
        "effective_port": resolution.effective_port,
        "source_by_field": resolution.source_by_field,
        "cli_args_present": resolution.cli_args_present,
        "env_overrides_present": resolution.env_overrides_present,
        "user_config_present": resolution.user_config_present,
        "project_local_config_present": resolution.project_local_config_present,
        "project_local_config_used": resolution.project_local_config_used,
        "error_code": resolution.error_code,
        "message": resolution.message,
        "default_scan_attempted": resolution.default_scan_attempted,
        "guessed_host": resolution.guessed_host,
        "effective_label": resolution.effective_label,
        "effective_environment": resolution.effective_environment,
        "effective_intended_target_type": resolution.effective_intended_target_type,
        "config_path": str(resolution.config_path) if resolution.config_path else None,
    }


def _config_value_host(config: dict[str, Any]) -> str | None:
    value = config.get("host")
    if value is None and isinstance(config.get("target"), dict):
        value = config["target"].get("osc_host")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _config_value_port(config: dict[str, Any]) -> int | None:
    value = config.get("port")
    if value is None and isinstance(config.get("target"), dict):
        value = config["target"].get("osc_port")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _current_os_recommendations() -> dict[str, Any]:
    return build_os_recommendations(platform_name=sys.platform)


def _state_value_dict(client: OscClient, path: str) -> dict[str, Any]:
    from m32_bridge.osc.discovery import read_state_value

    value = read_state_value(client.transport, path)
    return {
        "path": value.path,
        "raw_value": value.raw_value,
        "native_value": value.native_value,
        "display_value": value.display_value,
        "unit": value.unit,
        "value_type": value.value_type,
        "source": value.source,
        "revision": value.revision,
        "observed_at": value.observed_at.isoformat(),
        "fresh_until": value.fresh_until.isoformat(),
        "confidence": value.confidence,
        "stale": value.stale,
        "partial": value.partial,
        "support_status": value.support_status,
        "environment_label": value.environment_label,
    }


def _base_result(control: str, status: str) -> dict[str, Any]:
    return {
        "control": control,
        "status": status,
        "structured": True,
        "proposal_created": False,
        "write_operations": [],
        "osc_writes_sent": 0,
        "raw_osc_available": False,
        "arbitrary_path_available": False,
        "approval_token_supported": False,
        "console_write": False,
        "hardware_verified": False,
        "production_live_ready": False,
    }
