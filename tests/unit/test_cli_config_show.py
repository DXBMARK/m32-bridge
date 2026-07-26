from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_config_show(config_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    env.pop("M32_CONSOLE_HOST", None)
    env.pop("M32_CONSOLE_PORT", None)
    return subprocess.run(
        ["uv", "run", "m32-bridge", "config", "show", "--config-path", str(config_path), "--json"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _payload(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def test_config_show_reports_saved_non_secret_config(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "host": "192.0.2.10",
                "port": 10023,
                "label": "Lab",
                "intended_target_type": "emulator",
            }
        ),
        encoding="utf-8",
    )

    completed = _run_config_show(config_path)

    assert completed.returncode == 0, completed.stderr
    payload = _payload(completed)
    assert payload["ok"] is True
    assert payload["status"] == "CONFIGURED"
    assert payload["configured_host"] == "192.0.2.10"
    assert payload["configured_port"] == 10023
    assert payload["config_path"] == str(config_path)
    assert payload["source_by_field"]["host"] == "user_config"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert "token" not in json.dumps(payload).lower()
    assert "secret" not in json.dumps(payload).lower()


def test_config_show_missing_config_returns_no_console_host(tmp_path: Path):
    config_path = tmp_path / "missing-runtime.yaml"

    completed = _run_config_show(config_path)

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["status"] == "NO_CONSOLE_HOST"
    assert payload["error_code"] == "NO_CONSOLE_HOST"
    assert payload["configured_host"] is None
    assert payload["configured_port"] is None
    assert payload["config_path"] == str(config_path)
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_config_show_malformed_config_returns_structured_error(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text("host: [unterminated\n", encoding="utf-8")

    completed = _run_config_show(config_path)

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["status"] == "INVALID_CONFIG"
    assert payload["error_code"] == "INVALID_CONFIG"
    assert payload["config_path"] == str(config_path)
    assert payload["exception_type"] is not None
    assert payload["osc_writes_sent"] == 0
