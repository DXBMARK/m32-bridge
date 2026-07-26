from __future__ import annotations

import importlib


def _runtime_config_module():
    return importlib.import_module("m32_bridge.config.runtime")


def test_missing_host_returns_no_console_host_without_defaulting_to_localhost(tmp_path):
    runtime = _runtime_config_module()

    resolved = runtime.resolve_runtime_config(
        cli_args={},
        environ={},
        user_config_path=tmp_path / "missing-user.yaml",
        project_config_path=tmp_path / "missing-project.yaml",
        allow_project_local=False,
    )

    assert resolved.error_code == "NO_CONSOLE_HOST"
    assert resolved.effective_host is None
    assert resolved.effective_port is None
    assert resolved.default_scan_attempted is False
    assert resolved.guessed_host is None


def test_missing_host_runtime_output_guides_user_to_run_setup(tmp_path):
    runtime = _runtime_config_module()

    resolved = runtime.resolve_runtime_config(
        cli_args={},
        environ={},
        user_config_path=tmp_path / "missing-user.yaml",
        project_config_path=tmp_path / "missing-project.yaml",
        allow_project_local=False,
    )
    output = runtime.no_console_host_output(resolved)

    assert output["ok"] is False
    assert output["status"] == "NO_CONSOLE_HOST"
    assert output["error_code"] == "NO_CONSOLE_HOST"
    assert output["configured_host"] is None
    assert output["configured_port"] is None
    assert output["attempted_path"] == "/info"
    assert output["osc_writes_sent"] == 0
    assert output["hardware_verified"] is False
    assert any("m32-bridge setup" in item for item in output["recommendations"])


def test_missing_host_does_not_call_discovery_or_network_probe(monkeypatch, tmp_path):
    runtime = _runtime_config_module()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "scan_for_console_hosts", lambda *args, **kwargs: calls.append("scan"))
    monkeypatch.setattr(runtime, "probe_info", lambda *args, **kwargs: calls.append("probe"))

    runtime.resolve_runtime_config(
        cli_args={},
        environ={},
        user_config_path=tmp_path / "missing-user.yaml",
        project_config_path=tmp_path / "missing-project.yaml",
        allow_project_local=False,
    )

    assert calls == []
