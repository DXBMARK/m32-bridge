"""Read-only semantic MCP tools."""

from __future__ import annotations

from typing import Any

from m32_bridge.core.status import status_from_identity
from m32_bridge.diagnostics.runtime import console_status_not_connected_diagnostics, runtime_diagnostics
from m32_bridge.mcp.server import ToolRegistry, ToolSpec
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.discovery import discover_identity, read_state_value
from m32_bridge.osc.transport import OscEndpointError, OscTimeoutError


def _source(environ: str = "emulator") -> dict[str, Any]:
    return {"environment_label": environ, "hardware_verified": False, "freshness": "read_fresh"}


def console_status(client: OscClient) -> dict[str, Any]:
    import time

    started = time.perf_counter()
    try:
        discovery = discover_identity(client.transport)
    except (OscTimeoutError, OscEndpointError, OSError, TimeoutError) as exc:
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        return console_status_not_connected_diagnostics(
            host=client.transport.host,
            port=client.transport.port,
            latency_ms=latency_ms,
            exception=exc,
        )
    status = status_from_identity(discovery.identity, discovery.write_locked)
    data = status.__dict__ | {
        "status": "connected",
        "info_raw": discovery.info_raw,
        "info_fields": discovery.info_fields,
        "configured_host": client.transport.host,
        "configured_port": client.transport.port,
        "osc_writes_sent": 0,
        "write_operations": [],
    }
    return {
        "status": "connected",
        "connection_lifecycle": "connected",
        "data": data,
        "source": _source(status.environment_label),
        "osc_writes_sent": 0,
        "write_operations": [],
    }


def m32_runtime_diagnostics(
    client: OscClient,
) -> dict[str, Any]:
    return runtime_diagnostics(
        host=client.transport.host,
        port=client.transport.port,
        timeout=client.transport.timeout,
    )


def overview(client: OscClient) -> dict[str, Any]:
    discovery = discover_identity(client.transport)
    unsupported_or_timeout_paths: list[dict[str, str]] = []
    data: dict[str, Any] = {
        "connected": True,
        "info_raw": discovery.info_raw,
        "info_fields": discovery.info_fields,
        "configured_host": client.transport.host,
        "configured_port": client.transport.port,
    }

    node_message = _optional_request(client, "/node", "/", unsupported_or_timeout_paths=unsupported_or_timeout_paths)
    if node_message is not None and len(node_message.arguments) >= 2:
        children = str(node_message.arguments[1])
        data["nodes"] = [item for item in children.split(",") if item]
    else:
        data["nodes"] = []

    clock_sync: dict[str, str] = {}
    for key in ("clock_rate", "clock_source", "clock_mode", "aes50_a", "aes50_b", "expansion_card_sync"):
        address = f"/-stat/{key}"
        message = _optional_request(client, address, unsupported_or_timeout_paths=unsupported_or_timeout_paths)
        if message is not None and message.arguments:
            clock_sync[key] = str(message.arguments[0])
    data["clock_sync"] = clock_sync
    data["unsupported_or_timeout_paths"] = unsupported_or_timeout_paths

    if unsupported_or_timeout_paths:
        return {
            "status": "degraded",
            "error_code": "PARTIAL_CAPABILITY",
            "connection_lifecycle": "connected",
            "data": data,
            "unsupported_or_timeout_paths": unsupported_or_timeout_paths,
            "source": _source(discovery.identity.environment_label),
            "osc_writes_sent": 0,
            "write_operations": [],
            "hardware_verified": False,
        }
    return {
        "status": "connected",
        "connection_lifecycle": "connected",
        "data": data,
        "source": _source(discovery.identity.environment_label),
        "osc_writes_sent": 0,
        "write_operations": [],
        "hardware_verified": False,
    }


def list_channels(client: OscClient) -> dict[str, Any]:
    return {"data": [{"channel": 1, "headamp_gain": read_state_value(client.transport, "/ch/01/headamp/gain").display_value}], "source": _source()}


def get_channel(client: OscClient, channel: int = 1, include_processing: bool = False) -> dict[str, Any]:
    if channel != 1:
        return {"data": None, "error": "UNSUPPORTED_PATH", "source": _source()}
    value = read_state_value(client.transport, "/ch/01/headamp/gain")
    return {
        "data": {
            "channel": 1,
            "headamp_gain": value.native_value,
            "display_value": value.display_value,
            "revision": value.revision,
            "include_processing": include_processing,
        },
        "source": _source(),
    }


def get_bus(client: OscClient, bus: int = 1, kind: str = "bus") -> dict[str, Any]:
    return {"data": {"bus": bus, "kind": kind, "supported": True}, "source": _source()}


def get_routing(client: OscClient) -> dict[str, Any]:
    return {"data": client.routing(), "source": _source()}


def get_clock_sync(client: OscClient) -> dict[str, Any]:
    return {"data": client.clock_sync(), "source": _source()}


def get_meters(client: OscClient) -> dict[str, Any]:
    return {"data": {"positions": client.meters(), "not_per_channel_spectra": True}, "source": _source()}


def get_rta(client: OscClient) -> dict[str, Any]:
    return {"data": client.rta(), "source": _source()}


def capture_snapshot(client: OscClient) -> dict[str, Any]:
    return {"data": {"scope": "critical", "nodes": client.node("/")}, "source": _source()}


def compare_snapshots(_client: OscClient) -> dict[str, Any]:
    return {"data": {"differences": []}, "source": _source()}


def get_changes(_client: OscClient) -> dict[str, Any]:
    return {"data": {"changes": []}, "source": _source()}


def trace_signal(_client: OscClient) -> dict[str, Any]:
    return {"data": {"path": [], "confidence": "limited"}, "source": _source()}


def _optional_request(
    client: OscClient,
    address: str,
    *args: object,
    unsupported_or_timeout_paths: list[dict[str, str]],
):
    try:
        message = client.transport.request(address, *args)
    except (OscTimeoutError, OscEndpointError, OSError, TimeoutError) as exc:
        unsupported_or_timeout_paths.append({"path": address, "status": "unsupported_or_timeout", "reason": type(exc).__name__})
        return None
    if message.arguments and str(message.arguments[0]).upper() == "UNSUPPORTED_PATH":
        unsupported_or_timeout_paths.append({"path": address, "status": "unsupported_or_timeout", "reason": "UNSUPPORTED_PATH"})
        return None
    return message


READ_TOOL_HANDLERS = {
    "m32_console_status": console_status,
    "m32_runtime_diagnostics": m32_runtime_diagnostics,
    "m32_get_overview": overview,
    "m32_list_channels": list_channels,
    "m32_get_channel": get_channel,
    "m32_get_bus": get_bus,
    "m32_get_routing": get_routing,
    "m32_get_clock_sync": get_clock_sync,
    "m32_get_meters": get_meters,
    "m32_get_rta": get_rta,
    "m32_capture_snapshot": capture_snapshot,
    "m32_compare_snapshots": compare_snapshots,
    "m32_get_changes": get_changes,
    "m32_trace_signal": trace_signal,
}


def register_read_tools(registry: ToolRegistry) -> None:
    for name, handler in READ_TOOL_HANDLERS.items():
        registry.register(ToolSpec(name=name, read_only=True, sends_osc_writes=False, handler=handler))
