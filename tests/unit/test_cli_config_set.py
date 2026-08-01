from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

from m32_bridge.cli import setup_runtime

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


def test_setup_runtime_save_updates_same_runtime_config_file_after_success(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "host": "192.168.8.88",
                "port": 10023,
                "label": "Old",
                "intended_target_type": "unknown",
                "config_scope": "user",
            }
        ),
        encoding="utf-8",
    )

    payload = setup_runtime(
        host="192.168.8.99",
        port=10024,
        target_type="hardware",
        label="FOH",
        save=True,
        confirm_save=True,
        config_path=config_path,
        probe_result={
            "udp_info_probe_result": "CONNECTED",
            "response_address": ("192.168.8.99", 10024),
            "latency_ms": 3.5,
            "info_raw": ["M32", "4.09", "1.0", "FOH"],
        },
    )
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert payload["ok"] is True
    assert payload["saved"] is True
    assert payload["config_path"] == str(config_path)
    assert saved["host"] == "192.168.8.99"
    assert saved["port"] == 10024
    assert saved["label"] == "FOH"
    assert saved["intended_target_type"] == "hardware"
    assert payload["osc_writes_sent"] == 0


def test_setup_runtime_failed_probe_persists_config_without_rollback(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"
    original = {
        "schema_version": "1",
        "host": "192.168.8.88",
        "port": 10023,
        "label": "Old",
        "intended_target_type": "unknown",
        "config_scope": "user",
    }
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")

    payload = setup_runtime(
        host="192.168.8.99",
        port=10024,
        target_type="hardware",
        label="FOH",
        save=True,
        confirm_save=True,
        config_path=config_path,
        probe_result={
            "udp_info_probe_result": "TIMEOUT",
            "latency_ms": 500.0,
            "exception_type": "TimeoutError",
        },
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["saved"] is True
    assert payload["persistence_verified"] is True
    assert payload["connected"] is False
    assert payload["endpoint_verified"] is False
    assert payload["attempted_path"] == "/info"
    assert payload["verification_status"] == "CONNECT_TIMEOUT"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert saved["host"] == "192.168.8.99"
    assert saved["port"] == 10024
    assert saved["label"] == "FOH"
    assert saved["intended_target_type"] == "hardware"


def test_setup_runtime_save_offline_endpoint_reports_saved_but_not_verified(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"

    payload = setup_runtime(
        host="192.168.8.222",
        port=10123,
        target_type="hardware",
        label="Main Console",
        save=True,
        confirm_save=True,
        config_path=config_path,
        probe_result={
            "udp_info_probe_result": "NOT_CONNECTED",
            "latency_ms": 10.0,
            "exception_type": None,
        },
    )
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert payload["ok"] is True
    assert payload["saved"] is True
    assert payload["persistence_verified"] is True
    assert payload["probe_attempted"] is True
    assert payload["connected"] is False
    assert payload["endpoint_verified"] is False
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert saved["host"] == "192.168.8.222"
    assert saved["port"] == 10123
    assert saved["label"] == "Main Console"
    assert saved["intended_target_type"] == "hardware"


def test_setup_runtime_atomic_write_failure_skips_probe_and_preserves_old_config(tmp_path: Path, monkeypatch):
    import m32_bridge.config.runtime as runtime_config

    config_path = tmp_path / "runtime.yaml"
    original = {
        "schema_version": "1",
        "host": "192.168.8.88",
        "port": 10023,
        "intended_target_type": "unknown",
        "config_scope": "user",
    }
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")

    def fail_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(runtime_config.os, "replace", fail_replace)
    payload = setup_runtime(
        host="192.168.8.222",
        port=10123,
        target_type="hardware",
        label="Main Console",
        save=True,
        confirm_save=True,
        config_path=config_path,
        probe_result={"udp_info_probe_result": "CONNECTED", "response_address": ["192.168.8.222", 10123], "latency_ms": 1},
    )

    assert payload["ok"] is False
    assert payload["status"] == "CONFIG_WRITE_FAILED"
    assert payload["saved"] is False
    assert payload["persistence_verified"] is False
    assert payload["probe_attempted"] is False
    assert payload["attempted_path"] is None
    assert payload["exception_type"] == "OSError"
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original
