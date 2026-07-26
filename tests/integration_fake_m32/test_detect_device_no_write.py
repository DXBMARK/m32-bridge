from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from m32_bridge.fake_m32.server import FakeM32Server


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_detect_device_against_fake_m32_sends_no_writes_or_xremote():
    try:
        server = FakeM32Server().start()
    except PermissionError as exc:
        pytest.skip(f"local UDP unavailable in this sandbox: {exc}")
    try:
        env = os.environ.copy()
        env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
        completed = subprocess.run(
            [
                "uv",
                "run",
                "m32-bridge",
                "detect-device",
                "--host",
                server.address[0],
                "--port",
                str(server.address[1]),
                "--target-type",
                "emulator",
                "--json",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        assert payload["classification"] == "EMULATOR_CONNECTED"
        assert payload["connected"] is True
        assert payload["attempted_path"] == "/info"
        assert payload["osc_writes_sent"] == 0
        assert payload["hardware_verified"] is False
        assert payload["production_live_ready"] is False
        assert server.state.xremote_count == 0
        assert server.write_packets == []
    finally:
        server.stop()
