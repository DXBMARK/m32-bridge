from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_setup_without_host_returns_no_console_host_without_hanging():
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    env.pop("M32_CONSOLE_HOST", None)
    env.pop("M32_CONSOLE_PORT", None)
    completed = subprocess.run(
        ["uv", "run", "m32-bridge", "setup", "--json", "--no-save"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "NO_CONSOLE_HOST"
    assert payload["error_code"] == "NO_CONSOLE_HOST"
    assert payload["configured_host"] is None
    assert payload["configured_port"] is None
    assert payload["attempted_path"] == "/info"
    assert payload["latency_ms"] is None
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert any("m32-bridge setup" in item for item in payload["recommendations"])


def test_setup_missing_host_does_not_probe_or_scan(monkeypatch):
    from m32_bridge.cli import setup_runtime

    calls: list[str] = []
    monkeypatch.setattr("m32_bridge.config.runtime.scan_for_console_hosts", lambda *args, **kwargs: calls.append("scan"))
    monkeypatch.setattr("m32_bridge.config.runtime.probe_info", lambda *args, **kwargs: calls.append("probe"))

    payload = setup_runtime(host=None, port=None, target_type="unknown", save=False)

    assert payload["error_code"] == "NO_CONSOLE_HOST"
    assert payload["osc_writes_sent"] == 0
    assert calls == []
