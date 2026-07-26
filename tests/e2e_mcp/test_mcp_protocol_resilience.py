from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.server import ToolRegistry, create_mcp_stdio_server, invoke_tool, register_mvp_tools
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_mvp_tools(registry)
    return registry


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address, timeout=0.05))


def test_cancelled_tool_call_returns_structured_error_without_writes():
    server = FakeM32Server().start()
    try:
        result = invoke_tool(_registry(), "m32_get_channel", cancellation=lambda: True, client=_client(server), channel=1)

        assert result["ok"] is False
        assert result["error_code"] == "CANCELLED"
        assert result["result"]["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_timeout_returns_structured_error_without_handler_write():
    server = FakeM32Server().start()
    try:
        result = invoke_tool(_registry(), "m32_get_channel", timeout_seconds=0, client=_client(server), channel=1)

        assert result["ok"] is False
        assert result["error_code"] == "TIMEOUT"
        assert result["result"]["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_malformed_model_input_returns_validation_error_without_crash_or_writes():
    server = FakeM32Server().start()
    try:
        result = invoke_tool(_registry(), "m32_execute_proposal", proposal_id="missing")

        assert result["ok"] is False
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "TypeError" in result["result"]["exception"]
        assert result["result"]["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_concurrent_reads_are_structured_and_do_not_write():
    server = FakeM32Server().start()
    try:
        registry = _registry()
        client = _client(server)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _idx: invoke_tool(registry, "m32_get_channel", client=client, channel=1), range(8)))

        assert all(result["ok"] is True for result in results)
        assert all(result["tool"] == "m32_get_channel" for result in results)
        assert server.write_packets == []
    finally:
        server.stop()


def test_stdout_stderr_protocol_isolation_for_cli_health():
    completed = subprocess.run(
        [sys.executable, "-m", "m32_bridge", "health"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["control"] == "health"
    assert payload["structured"] is True


def test_cli_without_command_returns_non_tty_shell_guard():
    completed = subprocess.run(
        [sys.executable, "-m", "m32_bridge"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["error_code"] == "NON_INTERACTIVE_SHELL_REQUIRED"
    assert payload["osc_writes_sent"] == 0
    assert "m32-bridge setup" in payload["recommendations"]


def test_mcp_server_subcommand_starts_without_usage_or_json_diagnostics():
    process = subprocess.Popen(
        [sys.executable, "-m", "m32_bridge", "mcp-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.3)

        assert process.poll() is None
        process.terminate()
        stdout, _stderr = process.communicate(timeout=3)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=3)

    assert "usage:" not in stdout.lower()
    assert "health" not in stdout.lower()
    assert stdout == ""


def test_mcp_server_bootstrap_exposes_registry_tools_with_stdio_isolation():
    registry = _registry()
    server = create_mcp_stdio_server(registry)

    assert {"m32_console_status", "m32_get_channel", "m32_propose_changes"} <= set(registry.names())
    assert "raw_osc" not in " ".join(registry.names()).lower()
    assert "arbitrary_path" not in " ".join(registry.names()).lower()
    assert "approval_token" not in " ".join(registry.names()).lower()
    assert server.create_initialization_options().capabilities.tools is not None
