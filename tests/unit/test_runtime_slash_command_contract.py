from __future__ import annotations

import io
from pathlib import Path

import pytest


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def _runtime_result(tmp_path: Path) -> dict:
    app = tmp_path / "app"
    (app / ".venv").mkdir(parents=True, exist_ok=True)
    (app / "src" / "m32_bridge").mkdir(parents=True, exist_ok=True)
    (app / "pyproject.toml").write_text("[project]\nname='m32-mcp-bridge'\nversion='0.1.0'\n", encoding="utf-8")
    (app / "src" / "m32_bridge" / "__init__.py").write_text("", encoding="utf-8")
    launcher = tmp_path / "bin" / "m32-bridge"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    return {
        "tty_mode": "runtime",
        "ok": True,
        "status": "ok",
        "app_path": str(app),
        "launcher_path": str(launcher),
        "runtime_info": {"application_runtime_ready": True, "status": "ok", "uv_detected": True, "uv_path": "/opt/uv", "managed_python_version": "3.13.12"},
        "application_health": "healthy",
        "operational_state": "setup_required",
    }


def test_runtime_picker_commands_match_registry_exactly():
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY, RUNTIME_PICKER_ORDER
    from m32_bridge.installer.tty_app import RUNTIME_SLASH_COMMANDS

    picker = tuple(item["cmd"] for item in RUNTIME_SLASH_COMMANDS)
    assert picker == RUNTIME_PICKER_ORDER
    assert picker == tuple(RUNTIME_COMMAND_REGISTRY)
    assert len(picker) == len(set(picker))


def test_every_runtime_command_has_registered_handler():
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY
    from m32_bridge.installer.tty_app import runtime_handler_ids

    handler_ids = runtime_handler_ids()
    assert {spec.handler_id for spec in RUNTIME_COMMAND_REGISTRY.values()} == handler_ids


def test_every_runtime_handler_is_reachable(tmp_path):
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY
    from m32_bridge.installer.tty_app import dispatch_runtime_command

    calls: list[str] = []
    handlers = {
        spec.handler_id: (lambda result, marker=spec.handler_id, **kwargs: (calls.append(marker) or marker, marker == "runtime_exit"))
        for spec in RUNTIME_COMMAND_REGISTRY.values()
    }
    for command, spec in RUNTIME_COMMAND_REGISTRY.items():
        output, stop = dispatch_runtime_command(command, _runtime_result(tmp_path), handlers=handlers)
        assert output == spec.handler_id
        assert stop is (command == "/exit")
    assert calls == [spec.handler_id for spec in RUNTIME_COMMAND_REGISTRY.values()]


def test_runtime_help_lists_every_picker_command():
    from m32_bridge.installer.runtime_status import RUNTIME_PICKER_ORDER
    from m32_bridge.installer.tty_app import runtime_help_text

    help_text = runtime_help_text()
    for command in RUNTIME_PICKER_ORDER:
        assert command in help_text
    for label in ("Purpose", "Network", "Setup", "Writes", "Shell"):
        assert label in help_text


def test_status_shell_equivalent_is_not_health():
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY

    assert RUNTIME_COMMAND_REGISTRY["/status"].shell_equivalent == "m32-bridge status"
    assert RUNTIME_COMMAND_REGISTRY["/status refresh"].shell_equivalent == "m32-bridge status --refresh"
    assert "health" not in RUNTIME_COMMAND_REGISTRY["/status"].shell_equivalent


def test_health_and_status_use_distinct_handlers():
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY

    assert RUNTIME_COMMAND_REGISTRY["/health"].handler_id == "runtime_health"
    assert RUNTIME_COMMAND_REGISTRY["/status"].handler_id == "runtime_status"
    assert RUNTIME_COMMAND_REGISTRY["/status refresh"].handler_id == "runtime_status_refresh"
    assert len({RUNTIME_COMMAND_REGISTRY[key].handler_id for key in ("/health", "/status", "/status refresh")}) == 3


def test_health_performs_no_source_refresh(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(tty_app, "build_runtime_health", lambda result: {"marker": "health"})
    monkeypatch.setattr(tty_app, "render_runtime_health_panel", lambda payload, **kwargs: "HEALTH")
    monkeypatch.setattr(tty_app, "build_runtime_status", lambda *args, **kwargs: pytest.fail("status builder called"))
    output, stop = tty_app.dispatch_runtime_command("/health", _runtime_result(tmp_path))
    assert output == "HEALTH" and stop is False


def test_health_performs_no_console_probe(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(tty_app, "_execute_console_read", lambda *_args, **_kwargs: pytest.fail("console probe called"))
    output, stop = tty_app.dispatch_runtime_command("/health", _runtime_result(tmp_path))
    assert "HEALTH" in output and stop is False


def test_cli_status_and_tty_status_share_status_builder():
    from m32_bridge.installer import runtime_status, tty_app

    assert tty_app.build_runtime_status is runtime_status.build_runtime_status


@pytest.mark.parametrize("command", [
    "/help", "/status", "/status refresh", "/health", "/get-info", "/verify-device",
    "/doctor-runtime", "/mcp-config", "/contact", "/clear", "/exit",
])
def test_all_registered_non_setup_routes_execute_expected_handler(command, tmp_path):
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY
    from m32_bridge.installer.tty_app import dispatch_runtime_command

    spec = RUNTIME_COMMAND_REGISTRY[command]
    handlers = {spec.handler_id: lambda result, **kwargs: (f"TITLE {spec.handler_id}", command == "/exit")}
    output, stop = dispatch_runtime_command(command, _runtime_result(tmp_path), handlers=handlers)
    assert spec.handler_id in output
    assert stop is (command == "/exit")


def test_runtime_command_metadata_contract_is_complete():
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY

    for command, spec in RUNTIME_COMMAND_REGISTRY.items():
        assert spec.command == command
        assert spec.description
        assert spec.handler_id.startswith("runtime_")
        assert spec.view
        assert spec.shell_equivalent
        assert spec.network_scope in {
            "none", "official_source_https_only", "one_read_only_info_after_save", "configured_endpoint_read_only"
        }
        assert spec.visible_in_picker is True
    assert RUNTIME_COMMAND_REGISTRY["/setup"].read_only is False
    for command in ("/get-info", "/verify-device"):
        assert RUNTIME_COMMAND_REGISTRY[command].requires_console_config is True
        assert RUNTIME_COMMAND_REGISTRY[command].safe_to_retry_after_setup is True


@pytest.mark.parametrize("command", [
    "/help", "/status", "/status refresh", "/health", "/setup", "/get-info", "/verify-device",
    "/doctor-runtime", "/mcp-config", "/contact", "/clear", "/exit",
])
def test_all_slash_commands_survive_expected_failures(monkeypatch, tmp_path, command):
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(tty_app, "_runtime_body_rows", lambda result, **kwargs: [tty_app.TTYRow("text", "DASHBOARD")])
    monkeypatch.setattr(tty_app, "_requires_console_config", lambda value: False)
    handlers = {
        spec.handler_id: (lambda result, marker=spec.handler_id, **kwargs: (f"{marker.upper()} PANEL", marker == "runtime_exit"))
        for spec in tty_app.RUNTIME_COMMAND_REGISTRY.values()
    }
    monkeypatch.setattr(tty_app, "_runtime_handlers", lambda: handlers)
    if command == "/setup":
        monkeypatch.setattr(tty_app, "_setup_state_from_current_config", lambda: tty_app.SetupState())
        keys = [*command, "ENTER", "ESC", *"/exit", "ENTER"]
    elif command == "/exit":
        keys = [*command, "ENTER"]
    elif command == "/clear":
        keys = [*command, "ENTER", *"/exit", "ENTER"]
    else:
        keys = [*command, "ENTER", "ESC", *"/exit", "ENTER"]
    final, transcript = tty_app.run_tty_app(
        "posix",
        _runtime_result(tmp_path),
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (100, 26),
    )
    assert "Traceback" not in transcript
    assert not transcript.lstrip().startswith("{")
    assert final["runtime_exit_code"] == 0
    if command != "/exit":
        assert "DASHBOARD" in transcript


def test_complete_command_audit_panels_can_scroll_to_end():
    from m32_bridge.installer.tty_app import _next_panel_offset, _panel_window

    lines = [f"line {index}" for index in range(1, 81)]
    offset = 0
    for _ in range(20):
        offset = _next_panel_offset(offset, len(lines), 18, "PAGEDOWN")
    visible, footer = _panel_window(lines, offset, 7, view="status")
    assert visible[-1] == "line 80"
    assert "End of status" in footer


def test_clear_returns_to_dashboard_without_network(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(tty_app, "build_runtime_status", lambda *_args, **_kwargs: pytest.fail("network/status rebuild"))
    monkeypatch.setattr(tty_app, "render_tty_installer", lambda *args, **kwargs: "DASHBOARD")
    output, stop = tty_app.dispatch_runtime_command("/clear", _runtime_result(tmp_path))
    assert output == "DASHBOARD" and stop is False


def test_exit_returns_parent_shell_code_zero(tmp_path):
    from m32_bridge.installer.tty_app import dispatch_runtime_command, run_tty_app

    output, stop = dispatch_runtime_command("/exit", _runtime_result(tmp_path))
    assert stop is True and "parent" not in output.lower()
    final, _ = run_tty_app(
        "posix",
        _runtime_result(tmp_path),
        dry_run=False,
        color=False,
        key_reader=iter([*"/exit", "ENTER"]).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (80, 20),
    )
    assert final["runtime_exit_code"] == 0


def test_setup_result_uses_verification_attempted_not_double_negative(monkeypatch, tmp_path):
    from m32_bridge.installer.tty_app import _execute_setup_payload

    monkeypatch.setenv("HOME", str(tmp_path))
    panel = _execute_setup_payload(
        _runtime_result(tmp_path),
        host="192.0.2.10",
        port_text="10023",
        label=None,
        target_type="unknown",
        confirmation="CANCEL",
    )
    assert "Read-only verification attempted" in panel
    assert "Probe not run" not in panel
    assert "not_attempted" in panel


def test_setup_timeout_sets_config_valid_and_console_unreachable(monkeypatch, tmp_path):
    from m32_bridge import cli
    from m32_bridge.installer.tty_app import _execute_setup_payload

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        cli,
        "setup_info_probe",
        lambda *args, **kwargs: {
            "connected": False,
            "status": "TIMEOUT",
            "attempted_path": "/info",
            "latency_ms": None,
            "exception_type": "TimeoutError",
            "response": None,
        },
    )
    result = _runtime_result(tmp_path)
    panel = _execute_setup_payload(
        result,
        host="192.0.2.10",
        port_text="10023",
        label="FOH",
        target_type="hardware",
        confirmation="SAVE",
    )
    assert result["configuration_state"] == "valid"
    assert result["connection_state"] == "unreachable"
    assert result["operational_state"] == "console_unreachable"
    assert result["application_health"] == "healthy"
    assert result["last_console_error_code"] == "CONNECTION_TIMEOUT"
    assert "CONNECTION_TIMEOUT" in panel
    assert "RUNTIME READY" not in panel


def test_get_info_timeout_updates_last_known_connection(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    monkeypatch.setattr(
        tty_app,
        "_load_console_command_handlers",
        lambda: (
            lambda **kwargs: {"connected": False, "status": "TIMEOUT", "attempted_path": "/info", "latency_ms": None},
            lambda **kwargs: {},
        ),
    )
    result = _runtime_result(tmp_path)
    output, stop = tty_app.dispatch_runtime_command("/get-info", result)
    assert stop is False
    assert result["console_connection_status"] == "unreachable"
    assert result["last_console_attempted_path"] == "/info"
    assert result["last_console_error_code"] == "CONNECTION_TIMEOUT"
    assert result["last_console_check_at"]
    assert "Connection state" in output and "unreachable" in output


def test_get_info_timeout_shows_guidance(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    monkeypatch.setattr(
        tty_app,
        "_load_console_command_handlers",
        lambda: (
            lambda **kwargs: {"connected": False, "status": "TIMEOUT", "attempted_path": "/info"},
            lambda **kwargs: {},
        ),
    )
    output, _ = tty_app.dispatch_runtime_command("/get-info", _runtime_result(tmp_path))
    assert "CONNECTION_TIMEOUT" in output
    assert "Check console power, configured IP, UDP port, and network route." in output


def test_verify_device_timeout_remains_contained(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: 192.0.2.10\nport: 10023\nintended_target_type: hardware\n", encoding="utf-8")
    monkeypatch.setattr(
        tty_app,
        "_load_console_command_handlers",
        lambda: (
            lambda **kwargs: {},
            lambda **kwargs: {"connected": False, "status": "TIMEOUT", "attempted_path": "/info", "classification": "NOT_OBSERVED"},
        ),
    )
    output, stop = tty_app.dispatch_runtime_command("/verify-device", _runtime_result(tmp_path))
    assert stop is False
    assert "DEVICE VERIFICATION" in output
    assert "Traceback" not in output
    assert "Hardware verified" in output and "false" in output


def test_doctor_runtime_is_distinct_from_health(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    health, _ = tty_app.dispatch_runtime_command("/health", result)
    doctor, _ = tty_app.dispatch_runtime_command("/doctor-runtime", result)
    assert health != doctor
    assert "HEALTH" in health
    assert "DOCTOR RUNTIME" in doctor
    assert "REQUIRED IMPORTS" in doctor


def test_mcp_config_keeps_manual_no_write_contract(monkeypatch, tmp_path):
    from m32_bridge.installer import mcp_guidance, tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    captured: dict = {}
    original_renderer = mcp_guidance.render_mcp_guidance_text
    monkeypatch.setattr(
        mcp_guidance,
        "render_mcp_guidance_text",
        lambda payload, **kwargs: captured.update(payload) or original_renderer(payload, **kwargs),
    )
    result = _runtime_result(tmp_path)
    result["console_connection_status"] = "unreachable"
    before = set(tmp_path.rglob("*"))
    output, stop = tty_app.dispatch_runtime_command("/mcp-config", result, width=120)
    after = set(tmp_path.rglob("*"))
    assert stop is False
    assert "MCP CLIENT SETUP" in output
    assert "config write" in output.lower() and "false" in output.lower()
    assert captured["network_scan"] == "not_run"
    assert before == after
    assert result["console_connection_status"] == "unreachable"
