from __future__ import annotations

import json
import platform
import subprocess

from m32_bridge.__main__ import startup_verification
from m32_bridge.mcp.server import bootstrap_stdio_server


def test_macos_compileall_smoke_runs_with_py_module_command():
    completed = subprocess.run(["py", "-m", "compileall", "src", "tests"], check=False, capture_output=True, text=True)

    assert completed.returncode == 0


def test_macos_health_startup_returns_structured_json_without_side_effects():
    completed = subprocess.run(["py", "-m", "m32_bridge", "health"], check=False, capture_output=True, text=True)

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["control"] == "health"
    assert payload["structured"] is True
    assert payload["hardware_verified"] is False
    assert payload["checks"]["webui"] == "absent"
    assert payload["checks"]["production_live_ready"] is False


def test_macos_mcp_registry_bootstrap_smoke_has_no_webui_or_public_network():
    registry = bootstrap_stdio_server()
    startup = startup_verification()

    assert "m32_console_status" in registry.names()
    assert startup["python_version"].startswith("3.12.")
    assert startup["local_process"] is True
    assert startup["webui"] is False
    assert startup["database"] is False
    assert startup["microservices"] is False
    assert startup["network_side_effects"] is False
    assert startup["public_network_exposure"] is False
    assert startup["external_emulator"] is False
    assert startup["production_live_ready"] is False
    if platform.system() == "Darwin":
        assert startup["platform"] == "Darwin"
