"""Local operator controls for the M32 bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import yaml
from jsonschema import ValidationError

from m32_bridge.config.schemas import validate_with_schema
from m32_bridge.core.connection import ConnectionController
from m32_bridge.diagnostics.runtime import runtime_diagnostics
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
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
    return 0 if result.get("status") == "ok" else 1


def _run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "health":
        return health()
    if args.command == "doctor":
        return doctor(config_path=args.config)
    if args.command == "doctor-runtime":
        return runtime_diagnostics(host=args.host, port=args.port, timeout=args.timeout)
    if args.command == "snapshot":
        return operator_snapshot(_client_from_args(args))
    if args.command == "verify-connection":
        return verify_connection(_client_from_args(args))
    if args.command == "audit-tail":
        return audit_tail(args.audit_path, limit=args.limit)
    raise ValueError(f"unknown command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="m32_bridge", description="Local M32 bridge operator controls")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--config", type=Path, default=Path("config.example.yaml"))

    runtime_parser = subparsers.add_parser("doctor-runtime")
    runtime_parser.add_argument("--host", default=None)
    runtime_parser.add_argument("--port", type=int, default=None)
    runtime_parser.add_argument("--timeout", type=float, default=0.5)

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
