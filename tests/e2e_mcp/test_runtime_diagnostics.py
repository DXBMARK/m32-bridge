from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.server import RuntimeContext, RuntimeTarget, ToolRegistry, invoke_tool, register_mvp_tools


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_mvp_tools(registry)
    return registry


def _config_file(tmp_path: Path, server: FakeM32Server) -> Path:
    path = tmp_path / "m32-runtime.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "target": {
                    "kind": "fake_m32",
                    "osc_host": server.address[0],
                    "osc_port": server.address[1],
                },
                "transports": {"stdio": {"enabled": True}},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_terminal_direct_runtime_diagnostics_with_emulator_returns_connected():
    server = FakeM32Server().start()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "m32_bridge",
                "doctor-runtime",
                "--host",
                server.address[0],
                "--port",
                str(server.address[1]),
                "--timeout",
                "0.05",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert completed.returncode == 0
        assert completed.stderr == ""
        payload = json.loads(completed.stdout)
        assert payload["status"] == "ok"
        assert payload["udp_info_probe_result"] == "CONNECTED"
        assert payload["configured_host"] == server.address[0]
        assert payload["configured_port"] == server.address[1]
        assert payload["response_address"] == [server.address[0], server.address[1]]
        assert payload["attempted_path"] == "/info"
        assert payload["osc_writes_sent"] == 0
        assert payload["hardware_verified"] is False
        assert server.write_packets == []
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_mcp_sdk_stdio_runtime_diagnostics_with_env_copy_returns_connected(tmp_path: Path):
    server = FakeM32Server().start()
    try:
        config_path = _config_file(tmp_path, server)
        env = os.environ.copy()
        env["M32_CONFIG"] = str(config_path)
        env["M32_LAUNCHED_FROM"] = "claude_desktop"
        env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "m32_bridge", "mcp-server"],
            env=env,
            cwd=Path.cwd(),
        )

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "m32_runtime_diagnostics",
                    {},
                    read_timeout_seconds=timedelta(seconds=3),
                )

        payload = result.structuredContent
        assert payload["ok"] is True
        diagnostics = payload["result"]
        assert diagnostics["status"] == "ok"
        assert diagnostics["udp_info_probe_result"] == "CONNECTED"
        assert diagnostics["configured_host"] == server.address[0]
        assert diagnostics["configured_port"] == server.address[1]
        assert diagnostics["m32_config_present"] is True
        assert diagnostics["m32_config"]["exists"] is True
        assert diagnostics["launched_from"] == "claude_desktop"
        assert diagnostics["osc_writes_sent"] == 0
        assert diagnostics["hardware_verified"] is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_runtime_diagnostics_missing_endpoint_returns_structured_not_connected():
    result = invoke_tool(
        _registry(),
        "m32_runtime_diagnostics",
        runtime_context=RuntimeContext(RuntimeTarget(host=None, port=None)),
    )

    assert result["ok"] is False
    assert result["error_code"] == "NOT_CONNECTED"
    assert result["result"]["status"] == "not_connected"
    assert result["result"]["udp_info_probe_result"] == "NOT_CONNECTED"
    assert result["result"]["attempted_path"] == "/info"
    assert result["result"]["osc_writes_sent"] == 0
    assert result["result"]["hardware_verified"] is False


def test_console_status_timeout_envelope_includes_runtime_attempt_details():
    result = invoke_tool(
        _registry(),
        "m32_console_status",
        runtime_context=RuntimeContext(RuntimeTarget(host="127.0.0.1", port=9, timeout=0.01)),
    )

    assert result["ok"] is False
    assert result["error_code"] == "NOT_CONNECTED"
    assert result["result"]["configured_host"] == "127.0.0.1"
    assert result["result"]["configured_port"] == 9
    assert result["result"]["attempted_path"] == "/info"
    assert isinstance(result["result"]["latency_ms"], int)
    assert result["result"]["osc_writes_sent"] == 0
