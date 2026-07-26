from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_config_set(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    env.pop("M32_CONSOLE_HOST", None)
    env.pop("M32_CONSOLE_PORT", None)
    return subprocess.run(
        ["uv", "run", "m32-bridge", "config", "set", *args, "--json"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _payload(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def test_config_set_persists_user_editable_host_and_port(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"

    completed = _run_config_set("--host", "203.0.113.77", "--port", "10024", "--config-path", str(config_path))

    assert completed.returncode == 0, completed.stderr
    payload = _payload(completed)
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["status"] == "SAVED"
    assert payload["configured_host"] == "203.0.113.77"
    assert payload["configured_port"] == 10024
    assert saved["host"] == "203.0.113.77"
    assert saved["port"] == 10024
    assert payload["osc_writes_sent"] == 0


def test_config_set_allows_port_only_update_without_hardcoding_host(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(yaml.safe_dump({"host": "203.0.113.77", "port": 10023}), encoding="utf-8")

    completed = _run_config_set("--port", "10025", "--config-path", str(config_path))

    assert completed.returncode == 0, completed.stderr
    payload = _payload(completed)
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["configured_host"] == "203.0.113.77"
    assert payload["configured_port"] == 10025
    assert saved["host"] == "203.0.113.77"
    assert saved["port"] == 10025
    assert payload["osc_writes_sent"] == 0


def test_config_set_missing_host_does_not_guess_or_hardcode_production_host(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"

    completed = _run_config_set("--port", "10023", "--config-path", str(config_path))

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["error_code"] == "NO_CONSOLE_HOST"
    assert payload["configured_host"] is None
    assert config_path.exists() is False
    assert "192.168.8.88" not in json.dumps(payload)
    assert payload["osc_writes_sent"] == 0


def test_config_set_rejects_hardcoded_example_host_as_default(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"

    completed = _run_config_set("--config-path", str(config_path))

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["error_code"] == "NO_CONSOLE_HOST"
    assert payload["configured_host"] is None
    assert "M32_CONSOLE_HOST" not in json.dumps(payload)
    assert payload["osc_writes_sent"] == 0
