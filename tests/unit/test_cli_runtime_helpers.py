from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def managed_launcher_command(*args: str) -> list[str]:
    return ["uv", "run", "m32-bridge", *args]


def test_pyproject_declares_stable_m32_bridge_console_script():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["m32-bridge"] == "m32_bridge.__main__:main"


def test_managed_launcher_command_does_not_assume_global_py():
    command = managed_launcher_command("health")

    assert command[:3] == ["uv", "run", "m32-bridge"]
    assert "py" not in command


def test_uv_run_m32_bridge_health_returns_structured_no_write_output():
    env = os.environ.copy()
    env.pop("M32_CONSOLE_HOST", None)
    env.pop("M32_CONSOLE_PORT", None)
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")

    completed = subprocess.run(
        managed_launcher_command("health"),
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["control"] == "health"
    assert payload["status"] == "ok"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
