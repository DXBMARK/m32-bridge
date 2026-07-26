from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_external_emulator_detect_device_read_only_subset_does_not_fail_on_optional_limits():
    host = os.environ.get("M32_EXTERNAL_EMULATOR_HOST")
    port = os.environ.get("M32_EXTERNAL_EMULATOR_PORT")
    if not host or not port:
        pytest.skip("external emulator endpoint not configured")

    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    completed = subprocess.run(
        [
            "uv",
            "run",
            "m32-bridge",
            "detect-device",
            "--host",
            host,
            "--port",
            port,
            "--target-type",
            "emulator",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["connected"] is True
    assert payload["classification"] in {
        "EMULATOR_CONNECTED",
        "CONNECTED_UNVERIFIED",
        "HARDWARE_CANDIDATE",
    }
    assert payload["status"] != "NOT_CONNECTED"
    assert payload["error_code"] != "NOT_CONNECTED"
    assert payload["attempted_path"] == "/info"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    for item in payload.get("unsupported_or_timeout_paths", []):
        assert isinstance(item, dict)
        assert item["path"].startswith("/")
        assert "status" in item
        assert "reason" in item
        assert "exception_type" in item
