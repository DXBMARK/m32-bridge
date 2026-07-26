from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_startup_diagnostics_report_missing_launcher_without_silent_timeout():
    from m32_bridge.diagnostics.runtime import mcp_startup_diagnostics

    payload = mcp_startup_diagnostics(
        command="definitely-missing-m32-bridge",
        args=["mcp-server"],
        timeout_s=0.2,
        environ={},
    )

    assert payload["ok"] is False
    assert payload["status"] in {"LAUNCHER_NOT_FOUND", "MCP_STARTUP_FAILED"}
    assert payload["error_code"] in {"LAUNCHER_NOT_FOUND", "MCP_STARTUP_FAILED"}
    assert payload["command"] == "definitely-missing-m32-bridge"
    assert payload["transport"] == "stdio"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_mcp_startup_diagnostics_report_timeout_without_writes():
    from m32_bridge.diagnostics.runtime import mcp_startup_diagnostics

    payload = mcp_startup_diagnostics(
        command="uv",
        args=["run", "m32-bridge", "mcp-server"],
        timeout_s=0.01,
        environ={"UV_CACHE_DIR": "/private/tmp/uv-cache"},
        cwd=PROJECT_ROOT,
    )

    assert payload["ok"] is False
    assert payload["error_code"] in {"MCP_STARTUP_TIMEOUT", "MCP_STARTUP_FAILED"}
    assert payload["latency_ms"] is not None
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_mcp_startup_diagnostics_for_managed_launcher_mentions_stderr_stdout_contract():
    from m32_bridge.diagnostics.runtime import mcp_startup_diagnostics

    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    payload = mcp_startup_diagnostics(
        command="uv",
        args=["run", "m32-bridge", "mcp-server"],
        timeout_s=0.4,
        environ=env,
        cwd=PROJECT_ROOT,
    )

    assert payload["transport"] == "stdio"
    assert payload["stdout_protocol_clean"] is True
    assert payload["logs_to_stderr"] is True
    assert payload["opens_network_port"] is False
    assert payload["osc_writes_sent"] == 0
