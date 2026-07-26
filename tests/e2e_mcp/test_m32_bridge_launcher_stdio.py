from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    return env


def test_stable_launcher_works_through_managed_environment_without_global_py():
    completed = subprocess.run(
        ["uv", "run", "m32-bridge", "health"],
        cwd=PROJECT_ROOT,
        env=_env(),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["checks"]["mcp_primary_transport"] == "stdio"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_m32_bridge_mcp_server_starts_as_stdio_subprocess_without_terminal_window():
    process = subprocess.Popen(
        ["uv", "run", "m32-bridge", "mcp-server"],
        cwd=PROJECT_ROOT,
        env=_env(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.4)
        assert process.poll() is None
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)

    assert stdout == ""
    assert "usage:" not in stderr.lower()
    assert "traceback" not in stderr.lower()
