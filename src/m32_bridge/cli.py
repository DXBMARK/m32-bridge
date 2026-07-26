"""Local operator controls for the M32 bridge."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import yaml
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
from m32_bridge.core.connection import ConnectionController
from m32_bridge.diagnostics.device_identity import classify_device
from m32_bridge.diagnostics.os_recommendations import build_os_recommendations
from m32_bridge.diagnostics.runtime import runtime_diagnostics, setup_info_probe
from m32_bridge.diagnostics.runtime_output import runtime_output
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.discovery import discover_identity, read_state_value
from m32_bridge.osc.transport import OscTransport
from m32_bridge.state.snapshot import build_snapshot

DEFAULT_REQUIRED_PATHS = ("/ch/01/headamp/gain", "/rta/source")


def health() -> dict[str, Any]:
    result = _base_result("health", "ok")
    result["checks"] = {
        "cli": "ok",
        "mcp_primary_transport": "stdio",
        "webui": "absent",
        "production_live_ready": False,
    }
    result["hardware_verified"] = False
    return result


def doctor(*, config_path: Path = Path("config.example.yaml")) -> dict[str, Any]:
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

    probe = probe_result or setup_info_probe(str(host).strip(), port, timeout=timeout)
    response_address = probe.get("response_address")
    connected = probe.get("udp_info_probe_result") == "CONNECTED"
    latency_ms = probe.get("latency_ms")
    exception_type = probe.get("exception_type")

    if connected and response_address is not None and _response_address_mismatch(response_address, str(host).strip(), port):
        return runtime_output(
            ok=False,
            status="UNEXPECTED_RESPONSE_ADDRESS",
            error_code="UNEXPECTED_RESPONSE_ADDRESS",
            message="The /info response came from an unexpected address.",
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

    if not connected:
        error_code = "CONNECT_TIMEOUT" if exception_type and "Timeout" in str(exception_type) else "NOT_CONNECTED"
        return runtime_output(
            ok=False,
            status="NOT_CONNECTED",
            error_code=error_code,
            message="The configured endpoint did not respond to /info.",
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

    saved = False
    resolved_config_path = config_path or (default_project_config_path() if config_scope == "project_dev_test" else default_user_config_path())
    if save and confirm_save:
        save_runtime_config(
            path=resolved_config_path,
            host=str(host).strip(),
            port=port,
            intended_target_type=target_type,
            label=label,
            environment=environment,
            config_scope=config_scope,
        )
        saved = True

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
    payload["config_path"] = str(resolved_config_path)
    return payload


def detect_device_runtime(
    *,
    host: str | None,
    port: int | None,
    target_type: str,
    timeout: float = 0.5,
    probe_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
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


def doctor_runtime_command(
    *,
    host: str | None,
    port: int | None,
    timeout: float,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = runtime_diagnostics(host=host, port=port, timeout=timeout, environ=environ)
    payload["os_recommendations"] = _current_os_recommendations()
    return payload


def config_show_runtime(*, config_path: Path) -> dict[str, Any]:
    try:
        raw_config = _load_runtime_config_strict(config_path)
    except yaml.YAMLError as exc:
        payload = runtime_output(
            ok=False,
            status="INVALID_CONFIG",
            error_code="INVALID_CONFIG",
            message="Runtime config file is malformed.",
            configured_host=None,
            configured_port=None,
            attempted_path=None,
            latency_ms=None,
            exception_type=type(exc).__name__,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
        payload["config_path"] = str(config_path)
        return payload

    resolution = resolve_runtime_config(
        cli_args={},
        environ={},
        user_config_path=config_path,
        allow_project_local=False,
    )
    if resolution.error_code == "NO_CONSOLE_HOST":
        payload = no_console_host_output(resolution)
        payload["config_path"] = str(config_path)
        return payload

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
        from m32_bridge.interactive_shell import interactive_shell_loop, non_interactive_shell_required

        if sys.stdin.isatty():
            return interactive_shell_loop()
        result = non_interactive_shell_required(stdin_is_tty=False)
        print(json.dumps(result, sort_keys=True), file=sys.stdout)
        return 1
    if args.command == "mcp-server":
        from m32_bridge.mcp.server import run_mcp_stdio_server

        return run_mcp_stdio_server()
    try:
        result = _run_command(args)
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        print(json.dumps(_base_result(args.command, "error") | {"error": exc.__class__.__name__}), file=sys.stdout)
        return 1

    print(json.dumps(result, sort_keys=True), file=sys.stdout)
    return 0 if result.get("ok") is True or result.get("status") == "ok" else 1


def _run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "health":
        return health()
    if args.command == "doctor":
        return doctor(config_path=args.config)
    if args.command == "doctor-runtime":
        return doctor_runtime_command(host=args.host, port=args.port, timeout=args.timeout)
    if args.command == "setup":
        return setup_runtime(
            host=args.host,
            port=args.port,
            target_type=args.target_type,
            label=args.label,
            environment=args.environment,
            save=not args.no_save,
            confirm_save=args.yes,
            config_path=args.config_path,
            config_scope=args.config_scope,
            timeout=args.timeout,
        )
    if args.command == "detect-device":
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
    parser = argparse.ArgumentParser(prog="m32_bridge", description="Local M32 bridge operator controls")
    subparsers = parser.add_subparsers(dest="command", required=False)
    subparsers.add_parser("health")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--config", type=Path, default=Path("config.example.yaml"))

    runtime_parser = subparsers.add_parser("doctor-runtime")
    runtime_parser.add_argument("--host", default=None)
    runtime_parser.add_argument("--port", type=int, default=None)
    runtime_parser.add_argument("--timeout", type=float, default=0.5)

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


def _add_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=10023)
    parser.add_argument("--timeout", type=float, default=0.5)


def _client_from_args(args: argparse.Namespace) -> OscClient:
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
    }
