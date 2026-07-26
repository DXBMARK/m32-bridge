from __future__ import annotations

from pathlib import Path

import yaml


def test_setup_saves_non_secret_user_local_config_after_confirmation(tmp_path: Path):
    from m32_bridge.cli import setup_runtime

    config_path = tmp_path / "user" / "runtime.yaml"
    payload = setup_runtime(
        host="192.0.2.10",
        port=10023,
        target_type="emulator",
        label="Lab emulator",
        environment="lab",
        save=True,
        confirm_save=True,
        config_path=config_path,
        config_scope="user",
        probe_result={"udp_info_probe_result": "CONNECTED", "response_address": ["192.0.2.10", 10023], "latency_ms": 1},
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["saved"] is True
    assert payload["config_path"] == str(config_path)
    assert saved["host"] == "192.0.2.10"
    assert saved["port"] == 10023
    assert saved["intended_target_type"] == "emulator"
    assert "token" not in saved
    assert "secret" not in saved
    assert "claude_desktop_config" not in saved
    assert payload["osc_writes_sent"] == 0


def test_setup_does_not_save_without_operator_confirmation(tmp_path: Path):
    from m32_bridge.cli import setup_runtime

    config_path = tmp_path / "user" / "runtime.yaml"
    payload = setup_runtime(
        host="192.0.2.10",
        port=10023,
        target_type="emulator",
        save=True,
        confirm_save=False,
        config_path=config_path,
        probe_result={"udp_info_probe_result": "CONNECTED", "response_address": ["192.0.2.10", 10023], "latency_ms": 1},
    )

    assert payload["ok"] is True
    assert payload["saved"] is False
    assert config_path.exists() is False
    assert payload["osc_writes_sent"] == 0


def test_setup_supports_project_local_config_for_explicit_dev_test_scope(tmp_path: Path):
    from m32_bridge.cli import setup_runtime

    config_path = tmp_path / ".m32-bridge" / "runtime.local.yaml"
    payload = setup_runtime(
        host="127.0.0.1",
        port=10024,
        target_type="emulator",
        save=True,
        confirm_save=True,
        config_path=config_path,
        config_scope="project_dev_test",
        probe_result={"udp_info_probe_result": "CONNECTED", "response_address": ["127.0.0.1", 10024], "latency_ms": 1},
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["saved"] is True
    assert saved["config_scope"] == "project_dev_test"
    assert saved["host"] == "127.0.0.1"
    assert saved["port"] == 10024
    assert payload["osc_writes_sent"] == 0
