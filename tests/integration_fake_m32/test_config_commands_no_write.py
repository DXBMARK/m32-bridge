from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from m32_bridge.fake_m32.server import FakeM32Server


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_config_command(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "m32-bridge", "config", *args, "--json"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_config_commands_do_not_contact_or_write_to_fake_m32(tmp_path: Path):
    try:
        server = FakeM32Server().start()
    except PermissionError as exc:
        pytest.skip(f"local UDP unavailable in this sandbox: {exc}")
    try:
        env = os.environ.copy()
        env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
        env["M32_CONSOLE_HOST"] = server.address[0]
        env["M32_CONSOLE_PORT"] = str(server.address[1])
        config_path = tmp_path / "runtime.yaml"
        config_path.write_text(f"host: {server.address[0]}\nport: {server.address[1]}\n", encoding="utf-8")

        commands = [
            ("show", "--config-path", str(config_path)),
            ("validate", "--config-path", str(config_path)),
            ("set", "--host", server.address[0], "--port", str(server.address[1]), "--config-path", str(config_path)),
        ]
        results = [_run_config_command(*command, env=env) for command in commands]

        assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
        for result in results:
            payload = json.loads(result.stdout)
            assert payload["osc_writes_sent"] == 0
            assert payload["hardware_verified"] is False
        assert server.state.xremote_count == 0
        assert server.write_packets == []
    finally:
        server.stop()
