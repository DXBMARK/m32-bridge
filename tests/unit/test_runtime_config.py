from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
import yaml


def _runtime_config_module():
    return importlib.import_module("m32_bridge.config.runtime")


def test_runtime_config_accepts_host_port_label_environment_and_target_type():
    runtime = _runtime_config_module()

    config = runtime.RuntimeConfig(
        host="192.0.2.10",
        port=10023,
        label="FOH console",
        environment="lab",
        intended_target_type="hardware",
        config_path=Path("/tmp/m32-bridge/config.yaml"),
        config_scope="user",
    )

    assert config.host == "192.0.2.10"
    assert config.port == 10023
    assert config.label == "FOH console"
    assert config.environment == "lab"
    assert config.intended_target_type == "hardware"
    assert config.config_scope == "user"


def test_runtime_config_defaults_editable_port_only_when_host_is_present():
    runtime = _runtime_config_module()

    config = runtime.RuntimeConfig(host="192.0.2.10")

    assert config.port == 10023
    assert config.source_by_field["port"] == "default"


def test_runtime_config_rejects_invalid_target_type():
    runtime = _runtime_config_module()

    result = runtime.validate_runtime_config({"host": "192.0.2.10", "intended_target_type": "production"})

    assert result.ok is False
    assert result.error_code == "INVALID_CONFIG"
    assert "intended_target_type" in result.message


def test_runtime_config_source_metadata_identifies_user_config_values(tmp_path: Path):
    runtime = _runtime_config_module()
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text("host: 192.0.2.10\nport: 10024\n", encoding="utf-8")

    resolved = runtime.resolve_runtime_config(user_config_path=config_path, environ={}, cli_args={})

    assert resolved.effective_host == "192.0.2.10"
    assert resolved.effective_port == 10024
    assert resolved.source_by_field == {"host": "user_config", "port": "user_config"}
    assert resolved.user_config_present is True


def test_save_runtime_config_atomic_success_uses_same_directory_and_leaves_no_temp(tmp_path: Path):
    runtime = _runtime_config_module()
    config_path = tmp_path / "runtime.yaml"

    runtime.save_runtime_config(
        path=config_path,
        host="192.0.2.10",
        port=10023,
        intended_target_type="hardware",
        label="FOH",
    )
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert saved["host"] == "192.0.2.10"
    assert saved["port"] == 10023
    assert saved["intended_target_type"] == "hardware"
    assert saved["label"] == "FOH"
    assert list(tmp_path.glob(".runtime.yaml.*.tmp")) == []


def test_save_runtime_config_atomic_replaces_existing_without_partial_merge(tmp_path: Path):
    runtime = _runtime_config_module()
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        yaml.safe_dump({"schema_version": "1", "host": "old", "port": 10023, "label": "old", "extra": "remove"}),
        encoding="utf-8",
    )

    runtime.save_runtime_config(
        path=config_path,
        host="192.0.2.11",
        port=10024,
        intended_target_type="emulator",
    )
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert saved == {
        "schema_version": "1",
        "host": "192.0.2.11",
        "port": 10024,
        "intended_target_type": "emulator",
        "config_scope": "user",
    }
    assert list(tmp_path.glob(".runtime.yaml.*.tmp")) == []


def test_save_runtime_config_replace_failure_preserves_original_and_cleans_temp(tmp_path: Path, monkeypatch):
    runtime = _runtime_config_module()
    config_path = tmp_path / "runtime.yaml"
    original = "schema_version: '1'\nhost: old\nport: 10023\n"
    config_path.write_text(original, encoding="utf-8")

    def fail_replace(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(runtime.os, "replace", fail_replace)
    with pytest.raises(OSError):
        runtime.save_runtime_config(path=config_path, host="new", port=10024, intended_target_type="hardware")

    assert config_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".runtime.yaml.*.tmp")) == []


def test_save_runtime_config_write_failure_preserves_original_and_cleans_temp(tmp_path: Path, monkeypatch):
    runtime = _runtime_config_module()
    config_path = tmp_path / "runtime.yaml"
    original = "schema_version: '1'\nhost: old\nport: 10023\n"
    config_path.write_text(original, encoding="utf-8")

    def fail_fsync(_fd):
        raise OSError("fsync failed")

    monkeypatch.setattr(runtime.os, "fsync", fail_fsync)
    with pytest.raises(OSError):
        runtime.save_runtime_config(path=config_path, host="new", port=10024, intended_target_type="hardware")

    assert config_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".runtime.yaml.*.tmp")) == []


def test_save_runtime_config_does_not_use_admin_or_broad_permissions(tmp_path: Path, monkeypatch):
    runtime = _runtime_config_module()
    config_path = tmp_path / "runtime.yaml"
    chmod_calls: list[tuple[object, int]] = []

    monkeypatch.setattr(runtime.os, "chmod", lambda *args: chmod_calls.append(args), raising=False)
    runtime.save_runtime_config(path=config_path, host="192.0.2.10", port=10023, intended_target_type="unknown")

    assert config_path.parent == tmp_path
    assert chmod_calls == []
    assert os.geteuid() == os.geteuid()
