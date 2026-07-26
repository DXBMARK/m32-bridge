from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_validate(*args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    env.pop("M32_CONSOLE_HOST", None)
    env.pop("M32_CONSOLE_PORT", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["uv", "run", "m32-bridge", "config", "validate", *args, "--json"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _payload(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def test_config_validate_rejects_invalid_host(tmp_path: Path):
    completed = _run_validate("--host", "", "--port", "10023", "--config-path", str(tmp_path / "runtime.yaml"))

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["error_code"] == "INVALID_HOST"
    assert payload["configured_host"] is None
    assert payload["osc_writes_sent"] == 0


def test_config_validate_rejects_invalid_port(tmp_path: Path):
    completed = _run_validate("--host", "192.0.2.10", "--port", "70000", "--config-path", str(tmp_path / "runtime.yaml"))

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["error_code"] == "INVALID_PORT"
    assert payload["configured_host"] == "192.0.2.10"
    assert payload["configured_port"] is None
    assert payload["osc_writes_sent"] == 0


def test_config_validate_missing_host_returns_no_console_host(tmp_path: Path):
    completed = _run_validate("--config-path", str(tmp_path / "runtime.yaml"))

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["status"] == "NO_CONSOLE_HOST"
    assert payload["error_code"] == "NO_CONSOLE_HOST"
    assert payload["configured_host"] is None
    assert payload["configured_port"] is None
    assert payload["osc_writes_sent"] == 0


def test_config_validate_reports_source_precedence_cli_env_user_project(tmp_path: Path):
    user_path = tmp_path / "user-runtime.yaml"
    project_path = tmp_path / ".m32-bridge" / "runtime.local.yaml"
    project_path.parent.mkdir(parents=True)
    user_path.write_text(yaml.safe_dump({"host": "192.0.2.30", "port": 10030}), encoding="utf-8")
    project_path.write_text(yaml.safe_dump({"host": "192.0.2.40", "port": 10040}), encoding="utf-8")

    completed = _run_validate(
        "--host",
        "192.0.2.10",
        "--port",
        "10023",
        "--config-path",
        str(user_path),
        "--project-config-path",
        str(project_path),
        "--allow-project-local",
        env_overrides={"M32_CONSOLE_HOST": "192.0.2.20", "M32_CONSOLE_PORT": "10020"},
    )

    assert completed.returncode == 0, completed.stderr
    payload = _payload(completed)
    assert payload["ok"] is True
    assert payload["status"] == "VALID"
    assert payload["configured_host"] == "192.0.2.10"
    assert payload["configured_port"] == 10023
    assert payload["source_by_field"]["host"] == "cli"
    assert payload["source_by_field"]["port"] == "cli"
    assert payload["config_resolution"]["env_overrides_present"] is True
    assert payload["config_resolution"]["user_config_present"] is True
    assert payload["config_resolution"]["project_local_config_present"] is True
    assert payload["osc_writes_sent"] == 0
