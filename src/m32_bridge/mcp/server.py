"""MCP server registry and stdio bootstrap boundary."""

from __future__ import annotations

import anyio
import inspect
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import mcp.types as types
import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server

from m32_bridge.config.logging import configure_logging
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscEndpointError, OscTimeoutError, OscTransport

ToolHandler = Callable[..., dict[str, Any]]
_INTERNAL_TOOL_PARAMETERS = {
    "client",
    "store",
    "controller",
    "connection",
    "audit_writer",
}
_CLIENT_REQUIRED_NOT_INJECTED = {"m32_execute_proposal", "m32_rollback_proposal"}
_CONNECTION_EXCEPTIONS = (OscTimeoutError, OscEndpointError, OSError, TimeoutError)


@dataclass(frozen=True)
class RuntimeTarget:
    host: str | None
    port: int | None
    timeout: float = 0.5
    target_kind: str = "fake_m32"

    @property
    def configured(self) -> bool:
        return bool(self.host) and self.port is not None


@dataclass(frozen=True)
class RuntimeContext:
    target: RuntimeTarget

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "RuntimeContext":
        env = environ if environ is not None else os.environ
        config = _load_runtime_config(env)
        target_config = config.get("target", {}) if isinstance(config.get("target"), dict) else {}
        env_host = env.get("M32_CONSOLE_HOST")
        env_port = env.get("M32_CONSOLE_PORT")
        host = env_host or _string_or_none(target_config.get("osc_host"))
        port = _int_or_none(env_port if env_port is not None else target_config.get("osc_port"))
        target_kind = _string_or_none(target_config.get("kind")) or "fake_m32"
        return cls(RuntimeTarget(host=host, port=port, target_kind=target_kind))

    def client(self) -> OscClient | None:
        if not self.target.configured:
            return None
        return OscClient(OscTransport(str(self.target.host), int(self.target.port), timeout=self.target.timeout))


@dataclass(frozen=True)
class ToolSpec:
    name: str
    read_only: bool
    sends_osc_writes: bool
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        if spec.read_only and spec.sends_osc_writes:
            raise ValueError("read-only tools cannot send OSC writes")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)


def register_mvp_tools(registry: ToolRegistry) -> None:
    from m32_bridge.mcp.analysis_tools import register_analysis_tools
    from m32_bridge.mcp.read_tools import register_read_tools
    from m32_bridge.mcp.write_tools import register_write_tools

    registry.register(ToolSpec("m32_connect", read_only=True, sends_osc_writes=False, handler=m32_connect))
    registry.register(ToolSpec("m32_disconnect", read_only=False, sends_osc_writes=False, handler=m32_disconnect))
    registry.register(ToolSpec("m32_reconcile_state", read_only=True, sends_osc_writes=False, handler=m32_reconcile_state))
    register_read_tools(registry)
    register_analysis_tools(registry)
    register_write_tools(registry)


def invoke_tool(
    registry: ToolRegistry,
    name: str,
    *,
    runtime_mode: str = "OBSERVE",
    timeout_seconds: float | None = None,
    cancellation: Callable[[], bool] | None = None,
    runtime_context: RuntimeContext | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if cancellation is not None and cancellation():
        return _envelope(name, False, runtime_mode, _error_result("CANCELLED"), error_code="CANCELLED")
    if timeout_seconds is not None and timeout_seconds <= 0:
        return _envelope(name, False, runtime_mode, _error_result("TIMEOUT"), error_code="TIMEOUT")

    try:
        spec = registry.get(name)
        signature = inspect.signature(spec.handler)
        if runtime_mode != "OBSERVE" and "runtime_mode" in inspect.signature(spec.handler).parameters:
            kwargs.setdefault("runtime_mode", runtime_mode)
        if "client" in signature.parameters and "client" not in kwargs and name not in _CLIENT_REQUIRED_NOT_INJECTED:
            client = (runtime_context or RuntimeContext.from_env()).client()
            if client is None:
                return _envelope(name, False, runtime_mode, _not_connected_result("CONNECTION_CONFIG_MISSING"), error_code="NOT_CONNECTED")
            kwargs["client"] = client
        result = spec.handler(**kwargs)
    except TypeError as exc:
        return _envelope(name, False, runtime_mode, _error_result("VALIDATION_ERROR", exc), error_code="VALIDATION_ERROR")
    except _CONNECTION_EXCEPTIONS as exc:
        return _envelope(name, False, runtime_mode, _not_connected_result(type(exc).__name__, exc), error_code="NOT_CONNECTED")
    except Exception as exc:
        return _envelope(name, False, runtime_mode, _error_result(type(exc).__name__, exc), error_code=type(exc).__name__)
    ok = _tool_ok(result)
    return _envelope(name, ok, runtime_mode, result, error_code=None if ok else result.get("error_code"))


def m32_connect(target: str = "configured") -> dict[str, Any]:
    return {
        "status": "not_started",
        "target": target,
        "connection_lifecycle": "disconnected",
        "hardware_verified": False,
        "read_only_checks": [],
        "write_operations": [],
        "osc_writes_sent": 0,
    }


def m32_disconnect(reason: str = "operator_request", host_confirmed: bool = False) -> dict[str, Any]:
    return {
        "status": "disconnected",
        "reason": reason,
        "host_confirmed": host_confirmed,
        "connection_lifecycle": "disconnected",
        "hardware_verified": False,
        "write_operations": [],
        "osc_writes_sent": 0,
    }


def m32_reconcile_state(scope: str = "critical", proposal_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "not_connected",
        "scope": scope,
        "proposal_id": proposal_id,
        "connection_lifecycle": "disconnected",
        "reconciled": False,
        "hardware_verified": False,
        "write_operations": [],
        "osc_writes_sent": 0,
    }


def bootstrap_stdio_server() -> ToolRegistry:
    configure_logging()
    registry = ToolRegistry()
    register_mvp_tools(registry)
    return registry


def create_mcp_stdio_server(registry: ToolRegistry | None = None) -> Server:
    active_registry = registry or bootstrap_stdio_server()
    runtime_context = RuntimeContext.from_env()
    server = Server("m32-bridge-local")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [_mcp_tool_from_spec(active_registry.get(name)) for name in active_registry.names()]

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return invoke_tool(active_registry, name, runtime_context=runtime_context, **(arguments or {}))

    return server


def run_mcp_stdio_server() -> int:
    anyio.run(_run_mcp_stdio_server)
    return 0


async def _run_mcp_stdio_server() -> None:
    server = create_mcp_stdio_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _envelope(
    tool: str,
    ok: bool,
    runtime_mode: str,
    result: dict[str, Any],
    *,
    error_code: str | None = None,
) -> dict[str, Any]:
    hardware_verified = bool(result.get("hardware_verified", False))
    source = result.get("source")
    if not isinstance(source, dict):
        source = {"environment_label": "emulator", "hardware_verified": False, "freshness": "none"}
    return {
        "ok": ok,
        "tool": tool,
        "runtime_mode": getattr(runtime_mode, "value", runtime_mode),
        "connection_lifecycle": str(result.get("connection_lifecycle", "not_connected")),
        "verification_state": "HARDWARE_VERIFIED" if hardware_verified else "EMULATOR",
        "source": source,
        "hardware_verified": False if source.get("environment_label") == "emulator" else hardware_verified,
        "audit_id": result.get("audit_id"),
        "error_code": error_code,
        "result": _normalize_result(result),
    }


def _tool_ok(result: dict[str, Any]) -> bool:
    status = str(result.get("status", "")).lower()
    raw_error = result.get("error_code")
    error = "" if raw_error is None else str(raw_error).lower()
    return status not in {"denied", "failed", "error"} and not error


def _error_result(code: str, exc: Exception | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "error",
        "error_code": code,
        "write_operations": [],
        "osc_writes_sent": 0,
        "hardware_verified": False,
    }
    if exc is not None:
        result["exception"] = f"{type(exc).__name__}: {exc}"
    return result


def _not_connected_result(reason: str, exc: Exception | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "not_connected",
        "error_code": "NOT_CONNECTED",
        "reason": reason,
        "connection_lifecycle": "not_connected",
        "hardware_verified": False,
        "write_operations": [],
        "osc_writes_sent": 0,
    }
    if exc is not None:
        result["exception"] = f"{type(exc).__name__}: {exc}"
    return result


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    normalized.setdefault("write_operations", [])
    normalized.setdefault("osc_writes_sent", 0)
    normalized.setdefault("hardware_verified", False)
    return normalized


def _mcp_tool_from_spec(spec: ToolSpec) -> types.Tool:
    return types.Tool(
        name=spec.name,
        description=_tool_description(spec),
        inputSchema=_input_schema(spec.handler),
        annotations=types.ToolAnnotations(
            readOnlyHint=spec.read_only,
            destructiveHint=spec.sends_osc_writes,
            openWorldHint=False,
        ),
    )


def _tool_description(spec: ToolSpec) -> str:
    write_note = "May send bounded OSC writes only through the existing safety policy." if spec.sends_osc_writes else "Does not send OSC writes."
    return (
        "M32 Bridge MVP semantic tool. No raw OSC, arbitrary path, approval token, WebUI, "
        f"or production/live surface. {write_note}"
    )


def _input_schema(handler: ToolHandler) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in inspect.signature(handler).parameters.items():
        if name in _INTERNAL_TOOL_PARAMETERS:
            continue
        properties[name] = _schema_for_annotation(parameter.annotation)
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _schema_for_annotation(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty:
        return {}
    annotation_text = str(annotation)
    if "list" in annotation_text:
        return {"type": "array"}
    if "dict" in annotation_text or "Mapping" in annotation_text:
        return {"type": "object"}
    if annotation in {str} or "str" in annotation_text:
        return {"type": "string"}
    if annotation in {int} or "int" in annotation_text:
        return {"type": "integer"}
    if annotation in {float} or "float" in annotation_text:
        return {"type": "number"}
    if annotation in {bool} or "bool" in annotation_text:
        return {"type": "boolean"}
    try:
        json.dumps(annotation)
    except TypeError:
        return {}
    return {}


def _load_runtime_config(environ: dict[str, str]) -> dict[str, Any]:
    config_path = Path(environ.get("M32_CONFIG", "config.example.yaml"))
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


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
