from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from m32_bridge.cli import health
from m32_bridge.diagnostics.runtime import runtime_diagnostics


def assert_runtime_no_write(payload: Mapping[str, Any]) -> None:
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else payload
    assert result.get("osc_writes_sent") == 0
    assert result.get("hardware_verified") is False
    assert result.get("write_operations", []) == []


def assert_no_osc_write_packets(server: object) -> None:
    assert getattr(server, "write_packets") == []


class _NoWritePacketRecorder:
    write_packets: list[bytes] = []


def test_no_write_helper_accepts_flat_runtime_output():
    assert_runtime_no_write(health())


def test_no_write_helper_accepts_nested_mcp_result_output():
    payload = {
        "ok": True,
        "result": {
            "status": "ok",
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "write_operations": [],
        },
    }

    assert_runtime_no_write(payload)


def test_no_write_packet_helper_asserts_empty_server_write_log():
    assert_no_osc_write_packets(_NoWritePacketRecorder())


def test_runtime_diagnostics_missing_endpoint_is_no_write_without_network_probe():
    payload = runtime_diagnostics(environ={})

    assert payload["udp_info_probe_result"] == "NOT_CONNECTED"
    assert payload["attempted_path"] == "/info"
    assert_runtime_no_write(payload)
