from __future__ import annotations

import importlib
from pathlib import Path


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
