from __future__ import annotations

import json
import subprocess
import sys

from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.server import RuntimeContext, RuntimeTarget, ToolRegistry, invoke_tool, register_mvp_tools
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.codec import OscMessage
from m32_bridge.osc.transport import OscTimeoutError
from m32_bridge.osc.transport import OscTransport


READ_ONLY_SCRIPT = [
    ("m32_console_status", {}),
    ("m32_get_overview", {}),
    ("m32_list_channels", {}),
    ("m32_get_channel", {"channel": 1}),
    ("m32_get_routing", {}),
    ("m32_get_clock_sync", {}),
    ("m32_get_meters", {}),
    ("m32_get_rta", {}),
    ("m32_event_preflight", {}),
    ("m32_recommend_event_setup", {}),
    ("m32_capture_snapshot", {}),
    ("m32_compare_snapshots", {}),
    ("m32_get_changes", {}),
    ("m32_trace_signal", {}),
]


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_mvp_tools(registry)
    return registry


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address, timeout=0.05))


def _runtime_context(server: FakeM32Server) -> RuntimeContext:
    host, port = server.address
    return RuntimeContext(RuntimeTarget(host=host, port=port, timeout=0.05, target_kind="fake_m32"))


def test_console_status_without_client_returns_structured_not_connected():
    result = invoke_tool(_registry(), "m32_console_status", runtime_context=RuntimeContext(RuntimeTarget(host=None, port=None)))

    assert result["tool"] == "m32_console_status"
    assert result["ok"] is False
    assert result["error_code"] == "NOT_CONNECTED"
    assert result["result"]["status"] == "not_connected"
    assert result["result"]["hardware_verified"] is False
    assert result["result"]["write_operations"] == []
    assert result["result"]["osc_writes_sent"] == 0


def test_console_status_without_client_uses_runtime_context_when_available():
    server = FakeM32Server().start()
    try:
        result = invoke_tool(_registry(), "m32_console_status", runtime_context=_runtime_context(server))

        assert result["tool"] == "m32_console_status"
        assert result["ok"] is True
        assert result["result"]["data"]["target_kind"] == "fake_m32"
        assert result["result"]["data"]["info_raw"][0] == "M32"
        assert result["result"]["data"]["info_fields"]["model"] == "M32"
        assert result["result"]["data"]["info_fields"]["firmware_version"]
        assert result["result"]["data"]["configured_host"] == server.address[0]
        assert result["result"]["data"]["configured_port"] == server.address[1]
        assert result["hardware_verified"] is False
        assert result["result"]["data"]["hardware_verified"] is False
        assert result["result"]["write_operations"] == []
        assert result["result"]["osc_writes_sent"] == 0
        assert server.write_packets == []
    finally:
        server.stop()


def test_read_tool_without_client_uses_runtime_context_when_available():
    server = FakeM32Server().start()
    try:
        result = invoke_tool(_registry(), "m32_get_channel", channel=1, runtime_context=_runtime_context(server))

        assert result["tool"] == "m32_get_channel"
        assert result["ok"] is True
        assert result["result"]["data"]["channel"] == 1
        assert result["result"]["write_operations"] == []
        assert result["result"]["osc_writes_sent"] == 0
        assert server.write_packets == []
    finally:
        server.stop()


def test_overview_returns_degraded_when_info_succeeds_but_optional_paths_timeout():
    class PartialOverviewTransport:
        host = "192.168.8.88"
        port = 10023

        def request(self, address: str, *args: object) -> OscMessage:
            if address == "/info":
                return OscMessage("/info", ["M32", "X32 Emulator", "X32"])
            if address == "/node":
                raise OscTimeoutError("OSC request timed out")
            if address == "/-stat/clock_rate":
                return OscMessage(address, ["48k"])
            if address == "/-stat/clock_source":
                return OscMessage(address, ["internal"])
            raise OscTimeoutError("OSC request timed out")

    result = invoke_tool(_registry(), "m32_get_overview", client=OscClient(PartialOverviewTransport()))

    assert result["tool"] == "m32_get_overview"
    assert result["ok"] is False
    assert result["error_code"] == "PARTIAL_CAPABILITY"
    assert result["connection_lifecycle"] == "connected"
    assert result["result"]["data"]["connected"] is True
    assert result["result"]["data"]["configured_host"] == "192.168.8.88"
    assert result["result"]["data"]["configured_port"] == 10023
    assert result["result"]["unsupported_or_timeout_paths"]
    assert {item["path"] for item in result["result"]["unsupported_or_timeout_paths"]} >= {"/node", "/-stat/clock_mode"}
    assert result["result"]["osc_writes_sent"] == 0
    assert result["result"]["write_operations"] == []
    assert result["result"]["hardware_verified"] is False


def test_scripted_claude_read_only_conversation_is_structured_and_sends_no_writes():
    server = FakeM32Server().start()
    try:
        registry = _registry()
        context = _runtime_context(server)
        transcript = [invoke_tool(registry, tool, runtime_context=context, **kwargs) for tool, kwargs in READ_ONLY_SCRIPT]

        assert [turn["tool"] for turn in transcript] == [tool for tool, _kwargs in READ_ONLY_SCRIPT]
        assert all("result" in turn and "source" in turn for turn in transcript)
        assert all(turn["hardware_verified"] is False for turn in transcript)
        assert all(turn["result"]["write_operations"] == [] for turn in transcript)
        assert all(turn["result"]["osc_writes_sent"] == 0 for turn in transcript)
        assert server.write_packets == []
    finally:
        server.stop()


def test_scripted_read_only_conversation_has_no_raw_osc_arbitrary_path_or_execution_surface():
    registry = _registry()
    names = " ".join(registry.names()).lower()

    assert "raw_osc" not in names
    assert "arbitrary_path" not in names
    assert "approval_token" not in names
    assert "shell" not in names


def test_scripted_read_only_stdout_stderr_protocol_is_clean():
    completed = subprocess.run(
        [sys.executable, "-m", "m32_bridge", "health"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["structured"] is True
    assert payload["hardware_verified"] is False
