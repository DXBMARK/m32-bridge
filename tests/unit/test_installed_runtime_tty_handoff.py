from __future__ import annotations

import io
import json
import os
import stat
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_interactive_no_args_and_run_dispatch_to_runtime_tty(monkeypatch):
    from m32_bridge import cli
    from m32_bridge.installer import tty_app

    calls: list[str] = []
    monkeypatch.setattr(cli.sys, "stdin", TTYBuffer())
    monkeypatch.setattr(cli.sys, "stdout", TTYBuffer())
    monkeypatch.setattr(tty_app, "run_runtime_tty", lambda: calls.append("runtime") or 0)

    assert cli.main([]) == 0
    assert cli.main(["run"]) == 0
    assert calls == ["runtime", "runtime"]


def test_non_interactive_no_args_is_structured_and_never_starts_tty(monkeypatch, capsys):
    from m32_bridge import cli
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(cli.sys, "stdin", io.StringIO())
    monkeypatch.setattr(cli.sys, "stdout", io.StringIO())
    monkeypatch.setattr(tty_app, "run_runtime_tty", lambda: pytest.fail("TTY must not start"))

    assert cli.main([]) == 1
    payload = json.loads(cli.sys.stdout.getvalue())
    assert payload["error_code"] == "NON_INTERACTIVE_SHELL_REQUIRED"
    assert payload["started"] is False


def test_posix_handoff_execs_absolute_installed_launcher_without_bootstrap_pythonpath(tmp_path):
    from m32_bridge.installer.script_runtime import handoff_to_installed_runtime

    launcher = tmp_path / ".local" / "bin" / "m32-bridge"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    app = tmp_path / ".m32-bridge" / "app"
    (app / ".venv").mkdir(parents=True)
    captured = {}

    def fake_exec(path, argv, environ):
        captured.update(path=path, argv=argv, environ=environ)
        return 0

    result = {"launcher_path": str(launcher), "app_path": str(app)}
    assert handoff_to_installed_runtime("posix", result, exec_replace=fake_exec) == 0
    assert captured["path"] == str(launcher.resolve())
    assert captured["argv"] == [str(launcher.resolve()), "run"]
    assert captured["environ"]["M32_BRIDGE_INSTALLED_RUNTIME"] == "1"
    assert captured["environ"]["M32_BRIDGE_APP_DIR"] == str(app.resolve())
    assert "PYTHONPATH" not in captured["environ"]


def test_windows_handoff_runs_installed_launcher_once(tmp_path):
    from m32_bridge.installer.script_runtime import handoff_to_installed_runtime

    launcher = tmp_path / "M32Bridge" / "bin" / "m32-bridge.cmd"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("@echo off\r\n", encoding="utf-8")
    app = tmp_path / "M32Bridge" / "app"
    (app / ".venv").mkdir(parents=True)
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return type("Result", (), {"returncode": 0})()

    result = {"launcher_path": str(launcher), "app_path": str(app)}
    assert handoff_to_installed_runtime("windows", result, runner=fake_runner) == 0
    assert calls[0][0] == [str(launcher.resolve()), "run"]
    assert calls[0][1]["env"]["M32_BRIDGE_INSTALLED_RUNTIME"] == "1"
    assert len(calls) == 1


def test_generated_launchers_mark_installed_runtime_and_keep_frozen_policy(tmp_path):
    from m32_bridge.installer.script_runtime import _apply_user_local_install

    uv_bin = tmp_path / "uv"
    uv_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    posix_app = tmp_path / "posix" / "app"
    posix_launcher = tmp_path / "posix" / "bin" / "m32-bridge"
    _apply_user_local_install(
        "posix",
        {"app_path": str(posix_app), "launcher_path": str(posix_launcher), "install_root": str(posix_app.parent)},
        uv_bin=str(uv_bin),
    )
    text = posix_launcher.read_text(encoding="utf-8")
    assert "M32_BRIDGE_INSTALLED_RUNTIME=1" in text
    assert "--frozen" in text and "--no-build" in text and "--no-sync" in text
    assert "python -m m32_bridge.__main__" in text


def test_windows_launcher_marks_installed_runtime_and_dispatches_arguments(tmp_path):
    from m32_bridge.installer.script_runtime import _apply_user_local_install

    uv_bin = tmp_path / "uv.exe"
    uv_bin.write_text("binary", encoding="utf-8")
    app = tmp_path / "M32Bridge" / "app"
    launcher = tmp_path / "M32Bridge" / "bin" / "m32-bridge.cmd"
    _apply_user_local_install(
        "windows",
        {"app_path": str(app), "launcher_path": str(launcher), "install_root": str(app.parent)},
        uv_bin=str(uv_bin),
    )
    text = launcher.read_text(encoding="utf-8")
    assert "M32_BRIDGE_INSTALLED_RUNTIME=1" in text
    assert "--frozen" in text and "--no-build" in text and "--no-sync" in text
    assert "%*" in text


def test_runtime_import_provenance_rejects_bootstrap_source(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    bootstrap = tmp_path / "m32-bridge-bootstrap-case" / "src" / "m32_bridge" / "__init__.py"
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text("", encoding="utf-8")
    monkeypatch.setattr(tty_app, "_m32_bridge_module_path", lambda: bootstrap)

    with pytest.raises(RuntimeError, match="bootstrap"):
        tty_app.verify_runtime_import_provenance(
            {"M32_BRIDGE_INSTALLED_RUNTIME": "1", "M32_BRIDGE_APP_DIR": str(tmp_path / "installed")}
        )


def test_runtime_header_prompt_and_main_state_are_not_installer_branded(tmp_path):
    from m32_bridge.installer.tty_app import render_full_screen, strip_ansi

    result = {
        "tty_mode": "runtime",
        "app_path": str(tmp_path / "app"),
        "launcher_path": str(tmp_path / "bin" / "m32-bridge"),
        "runtime_info": {"application_runtime_ready": True, "managed_python_version": "3.13.14"},
        "console_configured": False,
        "console_connection_status": "not_checked",
        "status": "ok",
        "ok": True,
    }
    text = strip_ansi(render_full_screen("posix", result, dry_run=False, color=False, width=100, height=28))
    prompt_text = strip_ansi(render_full_screen("posix", result, dry_run=False, color=False, width=100, height=28, input_buffer="/"))
    assert "RUNTIME CONSOLE" in text
    assert "X32-BRIDGE MCP INSTALLER" not in text
    assert "m32-bridge > /" in prompt_text
    assert "NEXT ACTION" in text
    assert "Run /setup" in text


def test_command_registry_centralizes_setup_requirements():
    from m32_bridge.installer.tty_app import COMMAND_REGISTRY

    for command in ("/health", "/doctor-runtime", "/setup", "/mcp-config", "/help", "/contact", "/clear", "/exit"):
        assert COMMAND_REGISTRY[command]["requires_console_config"] is False
    for command in ("/get-info", "/verify-device"):
        assert COMMAND_REGISTRY[command]["requires_console_config"] is True
        assert COMMAND_REGISTRY[command]["read_only"] is True
        assert COMMAND_REGISTRY[command]["safe_to_retry_after_setup"] is True


def test_runtime_help_and_contact_never_present_themselves_as_installer(tmp_path):
    from m32_bridge.installer.tty_app import execute_installer_command

    result = {"tty_mode": "runtime", "app_path": str(tmp_path / "app"), "runtime_info": {}}
    help_text, _ = execute_installer_command("/help", result)
    contact_text, _ = execute_installer_command("/contact", result)
    assert "RUNTIME CONSOLE HELP" in help_text
    assert "RUNTIME CONSOLE" in contact_text
    assert "INSTALLER" not in help_text.upper()
    assert "INSTALLER" not in contact_text.upper()


def test_get_info_before_setup_is_classified_without_network_import_or_probe(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(tty_app, "_load_console_command_handlers", lambda: pytest.fail("network handlers imported"))
    output, stop = tty_app.execute_installer_command(
        "/get-info",
        {"tty_mode": "runtime", "app_path": str(tmp_path / "app")},
    )
    assert "SETUP REQUIRED" in output
    assert "SETUP_REQUIRED" in output
    assert "not_attempted" in output
    assert "OSC writes" in output and "0" in output
    assert stop is False


def test_health_before_setup_is_healthy_with_setup_required_readiness(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    output, stop = tty_app.execute_installer_command(
        "/health",
        {
            "tty_mode": "runtime",
            "app_path": str(tmp_path / "app"),
            "launcher_path": str(tmp_path / "bin" / "m32-bridge"),
            "runtime_info": {"application_runtime_ready": True},
        },
    )
    assert "Application runtime" in output and "healthy" in output
    assert "Console configured" in output and "false" in output
    assert "Operational readiness" in output and "setup_required" in output
    assert "not_checked" in output and "not_run" in output
    assert stop is False


def test_noninteractive_get_info_returns_setup_required_without_probe(monkeypatch, tmp_path, capsys):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli, "get_info_runtime", lambda **kwargs: pytest.fail("probe attempted"))
    assert cli.main(["get-info", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "SETUP_REQUIRED"
    assert payload["required_action"] == "m32-bridge setup"
    assert payload["attempted_path"] == "not_attempted"
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_noninteractive_verify_device_returns_setup_required_without_probe(monkeypatch, tmp_path, capsys):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli, "detect_device_runtime", lambda **kwargs: pytest.fail("probe attempted"))
    assert cli.main(["detect-device", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "SETUP_REQUIRED"
    assert payload["attempted_path"] == "not_attempted"
    assert payload["console_probe"] == "not_run"
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_unexpected_runtime_command_failure_is_contained_and_logged(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(tty_app, "_execute_command_impl", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("secret boom")))
    output, stop = tty_app.execute_installer_command(
        "/health",
        {"tty_mode": "runtime", "app_path": str(tmp_path / "app")},
    )
    assert "COMMAND_FAILED" in output
    assert "Traceback" not in output
    assert "secret boom" not in output
    assert stop is False
    logs = list((tmp_path / "logs").glob("runtime-*.log"))
    assert len(logs) == 1
    assert "RuntimeError" in logs[0].read_text(encoding="utf-8")
    if os.name != "nt":
        assert logs[0].stat().st_mode & 0o777 == 0o600


def test_runtime_accepts_next_command_after_unexpected_failure(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    original = tty_app._execute_command_impl
    attempts = {"count": 0}

    def fail_once(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("first command failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(tty_app, "_execute_command_impl", fail_once)
    result = {"tty_mode": "runtime", "app_path": str(tmp_path / "app"), "runtime_info": {}}
    failed, failed_stop = tty_app.execute_installer_command("/health", result)
    recovered, recovered_stop = tty_app.execute_installer_command("/health", result)
    assert "COMMAND_FAILED" in failed and failed_stop is False
    assert "Application runtime" in recovered and recovered_stop is False


def test_setup_required_enter_chains_setup_and_retries_read_only_command_once(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app
    from m32_bridge.runtime_preconditions import ConsolePrecondition

    monkeypatch.setenv("HOME", str(tmp_path))
    configured = {"value": False}
    monkeypatch.setattr(
        tty_app,
        "evaluate_console_precondition",
        lambda: (
            ConsolePrecondition(
                state="ready",
                configured=True,
                error_code=None,
                required_action=None,
                configured_host="console.example",
                configured_port=10023,
            )
            if configured["value"]
            else ConsolePrecondition.setup_required()
        ),
    )
    calls = []

    def fake_advance(state, result, *, color=False):
        configured["value"] = True
        return "SETUP SAVED", True

    def fake_read(action, result, *, color=False):
        calls.append(action)
        return "READ RETRIED"

    monkeypatch.setattr(tty_app, "_advance_setup_state", fake_advance)
    monkeypatch.setattr(tty_app, "_execute_console_read", fake_read)
    keys = [*"/get-info", "ENTER", "ENTER", "ENTER", *"/exit", "ENTER"]
    _, transcript = tty_app.run_tty_app(
        "posix",
        {"tty_mode": "runtime", "ok": True, "status": "ready", "app_path": str(tmp_path / "app"), "runtime_info": {}},
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (90, 24),
    )
    assert calls == ["/get-info"]
    assert "READ RETRIED" in transcript


def test_setup_required_escape_cancels_chain_and_tty_accepts_next_command(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(tty_app, "_runtime_has_console_config", lambda: False)
    monkeypatch.setattr(tty_app, "_execute_console_read", lambda *args, **kwargs: pytest.fail("original command ran"))
    keys = [*"/verify-device", "ENTER", "ENTER", "ESC", *"/health", "ENTER", *"/exit", "ENTER"]
    _, transcript = tty_app.run_tty_app(
        "posix",
        {"tty_mode": "runtime", "ok": True, "status": "ready", "app_path": str(tmp_path / "app"), "runtime_info": {}},
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (90, 24),
    )
    assert "Application runtime" in transcript


def test_exit_runtime_tty_returns_zero_without_shell_or_restart():
    from m32_bridge.installer.tty_app import run_tty_app

    result = {"tty_mode": "runtime", "ok": True, "status": "ok", "runtime_info": {}}
    final, _ = run_tty_app(
        "posix",
        result,
        dry_run=False,
        color=False,
        key_reader=iter(["/", "e", "x", "i", "t", "ENTER"]).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (80, 20),
    )
    assert final["ok"] is True


def test_health_without_config_is_runtime_healthy_but_setup_required(monkeypatch, tmp_path):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    payload = cli.health()
    assert payload["ok"] is True
    assert payload["application_runtime"] == "healthy"
    assert payload["console_configured"] is False
    assert payload["operational_readiness"] == "setup_required"
    assert payload.get("error_code") is None
    assert payload["precondition_state"] == "setup_required"
    assert payload["required_action"] == "m32-bridge setup"
    assert payload["attempted_path"] == "not_attempted"
    assert payload["console_probe"] == "not_run"
    assert payload["network_scan"] == "not_run"
    assert payload["checks"]["network_scan"] == "not_run"


def test_health_with_empty_config_is_not_ready(monkeypatch, tmp_path):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("", encoding="utf-8")
    payload = cli.health()
    assert payload["ok"] is True
    assert payload["console_configured"] is False
    assert payload["operational_readiness"] == "setup_required"
    assert payload["console_connection"] == "not_checked"


def test_health_with_malformed_config_is_config_invalid(monkeypatch, tmp_path):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: [unterminated", encoding="utf-8")
    payload = cli.health()
    assert payload["ok"] is False
    assert payload["status"] == "CONFIG_INVALID"
    assert payload["error_code"] == "CONFIG_INVALID"
    assert payload["application_runtime"] == "healthy"
    assert payload["next_action"] == "Repair the saved configuration or run m32-bridge setup"
    assert payload["attempted_path"] == "not_attempted"
    assert payload["console_probe"] == "not_run"


def test_health_with_valid_config_is_ready_without_probe(monkeypatch, tmp_path):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    payload = cli.health()
    assert payload["ok"] is True
    assert payload["console_configured"] is True
    assert payload["operational_readiness"] == "ready"
    assert payload["console_connection"] == "not_checked"
    assert payload["console_probe"] == "not_run"


def test_cli_invalid_config_is_not_setup_required(monkeypatch, tmp_path, capsys):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: [unterminated", encoding="utf-8")
    monkeypatch.setattr(cli, "get_info_runtime", lambda **kwargs: pytest.fail("network handler called"))
    assert cli.main(["get-info", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "CONFIG_INVALID"
    assert payload["attempted_path"] == "not_attempted"


def test_tty_invalid_config_is_not_setup_required(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: [unterminated", encoding="utf-8")
    monkeypatch.setattr(tty_app, "_load_console_command_handlers", lambda: pytest.fail("network handler called"))
    output, stop = tty_app.execute_installer_command(
        "/get-info", {"tty_mode": "runtime", "app_path": str(tmp_path / "app")}
    )
    assert "CONFIG_INVALID" in output
    assert "SETUP REQUIRED" not in output
    assert stop is False


def test_safe_retry_metadata_requires_all_three_flags(monkeypatch):
    from m32_bridge.installer import tty_app

    metadata = tty_app.COMMAND_REGISTRY["/get-info"]
    assert tty_app._can_retry_after_setup("/get-info") is True
    for key in ("requires_console_config", "read_only", "safe_to_retry_after_setup"):
        monkeypatch.setitem(metadata, key, False)
        assert tty_app._can_retry_after_setup("/get-info") is False
        monkeypatch.setitem(metadata, key, True)


def test_safe_retry_requires_ready_precondition(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app
    from m32_bridge.runtime_preconditions import ConsolePrecondition

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        tty_app,
        "evaluate_console_precondition",
        lambda: ConsolePrecondition.setup_required(),
    )
    assert tty_app._retry_is_ready("/get-info") is False


def test_command_requiring_config_is_blocked_even_when_not_safe_to_retry(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app
    from m32_bridge.runtime_preconditions import ConsolePrecondition

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setitem(tty_app.COMMAND_REGISTRY["/get-info"], "read_only", False)
    calls = []
    setup_calls = []
    monkeypatch.setattr(tty_app, "evaluate_console_precondition", lambda: ConsolePrecondition.setup_required())
    monkeypatch.setattr(tty_app, "_execute_console_read", lambda *args, **kwargs: calls.append(args[0]) or "HANDLER CALLED")
    monkeypatch.setattr(tty_app, "_setup_state_from_current_config", lambda: setup_calls.append("setup") or pytest.fail("unsafe command became pending"))
    keys = [*"/get-info", "ENTER", "ENTER", "ESC", *"/exit", "ENTER"]
    _, transcript = tty_app.run_tty_app(
        "posix",
        {"tty_mode": "runtime", "ok": True, "status": "ready", "app_path": str(tmp_path / "app"), "runtime_info": {}},
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (90, 24),
    )
    assert calls == []
    assert setup_calls == []
    assert "SETUP REQUIRED" in transcript
    assert "Run /setup" in transcript


def test_config_invalid_command_handler_is_never_called_and_does_not_start_setup(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app
    from m32_bridge.runtime_preconditions import ConsolePrecondition

    monkeypatch.setattr(tty_app, "evaluate_console_precondition", lambda: ConsolePrecondition.config_invalid())
    monkeypatch.setattr(tty_app, "_execute_console_read", lambda *args, **kwargs: pytest.fail("handler called"))
    monkeypatch.setattr(tty_app, "_setup_state_from_current_config", lambda: pytest.fail("setup chain started"))
    keys = [*"/get-info", "ENTER", "ENTER", "ESC", *"/exit", "ENTER"]
    _, transcript = tty_app.run_tty_app(
        "posix",
        {"tty_mode": "runtime", "ok": True, "status": "ready", "app_path": str(tmp_path / "app"), "runtime_info": {}},
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (90, 24),
    )
    assert "CONFIG_INVALID" in transcript
    assert "SETUP REQUIRED" not in transcript


@pytest.mark.parametrize(
    ("contents", "expected_state"),
    [
        ("host: console.example\nport: 0\n", "config_invalid"),
        ("host: console.example\nport: -1\n", "config_invalid"),
        ("host: console.example\nport: 65536\n", "config_invalid"),
        ("host: console.example\nport: nope\n", "config_invalid"),
        ("host: ''\n", "setup_required"),
        ("host: console.example\nport: 10023\n", "ready"),
        ("host: 192.0.2.10\n", "ready"),
    ],
)
def test_saved_endpoint_values_have_canonical_precondition_states(monkeypatch, tmp_path, contents, expected_state):
    from m32_bridge.runtime_preconditions import evaluate_console_precondition

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(contents, encoding="utf-8")
    assert evaluate_console_precondition().state == expected_state


def test_environment_port_out_of_range_is_config_invalid(monkeypatch, tmp_path):
    from m32_bridge.runtime_preconditions import evaluate_console_precondition

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("M32_CONSOLE_HOST", "console.example")
    monkeypatch.setenv("M32_CONSOLE_PORT", "70000")
    assert evaluate_console_precondition().state == "config_invalid"


def test_saved_non_string_host_is_config_invalid(monkeypatch, tmp_path):
    from m32_bridge.runtime_preconditions import evaluate_console_precondition

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host:\n  - console.example\nport: 10023\n", encoding="utf-8")
    assert evaluate_console_precondition().state == "config_invalid"


def test_runtime_main_screen_distinguishes_invalid_config():
    from m32_bridge.installer.tty_app import render_full_screen, strip_ansi

    result = {
        "tty_mode": "runtime",
        "ok": True,
        "status": "ready",
        "runtime_info": {},
        "console_configured": False,
        "console_precondition_state": "config_invalid",
        "console_connection_status": "not_checked",
    }
    text = strip_ansi(render_full_screen("posix", result, dry_run=False, color=False, width=100, height=28))
    assert "Configuration state" in text and "invalid" in text
    assert "Repair the saved configuration or run /setup" in text


def test_manual_setup_opens_with_malformed_config_and_cancel_keeps_tty_alive(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: [unterminated\n", encoding="utf-8")
    monkeypatch.setattr(tty_app, "_load_console_command_handlers", lambda: pytest.fail("network handlers imported"))
    keys = [*"/setup", "ENTER", "ESC", *"/health", "ENTER", "ESC", *"/exit", "ENTER"]
    final, transcript = tty_app.run_tty_app(
        "posix",
        {
            "tty_mode": "runtime",
            "ok": True,
            "status": "ready",
            "app_path": str(tmp_path / "app"),
            "runtime_info": {},
            "console_precondition_state": "config_invalid",
        },
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (100, 30),
    )
    assert "Existing configuration is unreadable" in transcript
    assert "Traceback" not in transcript
    assert "Application runtime" in transcript
    assert final["runtime_exit_code"] == 0
    assert config.read_text(encoding="utf-8") == "host: [unterminated\n"


def test_manual_setup_malformed_config_save_replaces_file_atomically_and_becomes_ready(monkeypatch, tmp_path):
    from m32_bridge import cli
    from m32_bridge.installer import tty_app
    from m32_bridge.runtime_preconditions import evaluate_console_precondition

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: [unterminated\n", encoding="utf-8")
    probes = []
    monkeypatch.setattr(
        cli,
        "setup_info_probe",
        lambda *args, **kwargs: probes.append({"args": args, **kwargs}) or {
            "connected": False,
            "status": "TIMEOUT",
            "classification": "NOT_OBSERVED",
            "attempted_path": "/info",
            "latency_ms": None,
            "exception_type": "TimeoutError",
            "response": None,
        },
    )
    keys = [
        *"/setup", "ENTER",
        *"console.example", "ENTER",
        "ENTER",
        "ENTER",
        "ENTER",
        *"SAVE", "ENTER",
        "ESC",
        *"/exit", "ENTER",
    ]
    final, transcript = tty_app.run_tty_app(
        "posix",
        {
            "tty_mode": "runtime",
            "ok": True,
            "status": "ready",
            "app_path": str(tmp_path / "app"),
            "runtime_info": {},
            "console_precondition_state": "config_invalid",
        },
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (100, 30),
    )
    assert "Traceback" not in transcript
    assert len(probes) == 1
    assert evaluate_console_precondition().state == "ready"
    assert "console.example" in config.read_text(encoding="utf-8")
    assert list(config.parent.glob(f".{config.name}.*.tmp")) == []
    assert final["runtime_exit_code"] == 0


def test_manual_setup_malformed_config_does_not_probe_before_save(monkeypatch, tmp_path):
    from m32_bridge import cli
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: [unterminated\n", encoding="utf-8")
    monkeypatch.setattr(cli, "setup_info_probe", lambda **kwargs: pytest.fail("probe ran before SAVE"))
    state = tty_app._setup_state_from_current_config()
    assert state.config_path.endswith("runtime.yaml")
    assert state.current_values == {"target_type": "unknown"}
    assert state.configuration_unreadable is True


def test_manual_setup_state_creation_failure_is_contained_and_tty_survives(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(
        tty_app,
        "_setup_state_from_current_config",
        lambda: (_ for _ in ()).throw(RuntimeError("unsafe setup detail")),
    )
    keys = [*"/setup", "ENTER", "ESC", *"/exit", "ENTER"]
    final, transcript = tty_app.run_tty_app(
        "posix",
        {
            "tty_mode": "runtime",
            "ok": True,
            "status": "ready",
            "app_path": str(tmp_path / "app"),
            "runtime_info": {},
            "console_precondition_state": "config_invalid",
        },
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=TTYBuffer(),
        size_provider=lambda: (100, 30),
    )
    assert "CONFIG_INVALID" in transcript
    assert "unsafe setup detail" not in transcript
    assert "Traceback" not in transcript
    assert final["runtime_exit_code"] == 0


def test_installer_status_invalid_config_is_not_configured(monkeypatch, tmp_path):
    from m32_bridge.installer.tty_app import render_status_text, strip_ansi

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: console.example\nport: 0\n", encoding="utf-8")
    text = strip_ansi(render_status_text({"status": "ready", "runtime_info": {}, "platform_info": {}}))
    assert "Configured" in text and "false" in text
    assert "Configuration state" in text and "invalid" in text
    assert "Repair the saved configuration or run /setup" in text


def test_installer_health_network_scan_is_not_run_string(monkeypatch):
    from m32_bridge.installer import tty_app

    captured = {}
    monkeypatch.setattr(tty_app, "render_health_panel", lambda payload, **kwargs: captured.update(payload) or "HEALTH")
    output, stop = tty_app.execute_installer_command(
        "/health",
        {"tty_mode": "installer", "app_path": "/tmp/app", "runtime_info": {}},
    )
    assert output == "HEALTH" and stop is False
    assert captured["network_scan"] == "not_run"


def test_diagnostic_log_created_with_secure_permissions_and_redaction(tmp_path):
    from m32_bridge.installer.runtime_faults import write_runtime_diagnostic_log

    secret = (
        "Authorization: Bearer bearer-secret\nAuthorization: Basic basic-secret\n"
        "token=token-secret password=password-secret secret=hidden api_key=key-one api-key=key-two "
        "https://user:url-password@example.com"
    )
    try:
        raise RuntimeError(secret)
    except RuntimeError as exc:
        path = write_runtime_diagnostic_log(tmp_path / "logs", exc)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    for value in ("bearer-secret", "basic-secret", "token-secret", "password-secret", "hidden", "key-one", "key-two", "url-password"):
        assert value not in text
    if os.name != "nt":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_diagnostic_log_uses_exclusive_creation(monkeypatch, tmp_path):
    from m32_bridge.installer import runtime_faults

    monkeypatch.setattr(runtime_faults, "_new_log_name", lambda: "runtime-fixed.log")
    first = runtime_faults.write_runtime_diagnostic_log(tmp_path, RuntimeError("one"))
    second = runtime_faults.write_runtime_diagnostic_log(tmp_path, RuntimeError("two"))
    assert first is not None
    assert second is None
    assert first.read_text(encoding="utf-8").find("one") >= 0


def test_diagnostic_log_failure_does_not_escape_runtime_boundary(monkeypatch, tmp_path):
    from m32_bridge.installer import runtime_faults, tty_app

    original = tty_app._execute_command_impl
    attempts = {"count": 0}

    def fail_once(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("command failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(tty_app, "_execute_command_impl", fail_once)
    monkeypatch.setattr(runtime_faults, "write_runtime_diagnostic_log", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")))
    result = {"tty_mode": "runtime", "app_path": str(tmp_path / "app"), "runtime_info": {}}
    failed, stop = tty_app.execute_installer_command("/health", result)
    recovered, recovered_stop = tty_app.execute_installer_command("/health", result)
    assert "COMMAND_FAILED" in failed and "unavailable" in failed
    assert "Traceback" not in failed and stop is False
    assert "Application runtime" in recovered and recovered_stop is False


def test_windows_handoff_nonzero_is_controlled_and_invoked_once(tmp_path):
    from m32_bridge.installer.script_runtime import handoff_to_installed_runtime

    launcher = tmp_path / "bin" / "m32-bridge.cmd"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("@echo off\r\n", encoding="utf-8")
    app = tmp_path / "app"
    (app / ".venv").mkdir(parents=True)
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return type("Result", (), {"returncode": 1})()

    with pytest.raises(RuntimeError, match="handoff"):
        handoff_to_installed_runtime(
            "windows", {"launcher_path": str(launcher), "app_path": str(app)}, runner=runner
        )
    assert len(calls) == 1


def test_windows_handoff_failure_is_classified_by_installer_main(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    applied = _successful_install_payload(tmp_path)
    handoff_calls = []
    rendered = {}

    monkeypatch.setattr(script_runtime, "build_install_result", lambda **kwargs: {"installer_can_continue": True})
    monkeypatch.setattr(script_runtime, "perform_apply_install", lambda *args, **kwargs: applied)

    def failed_handoff(surface, result):
        handoff_calls.append((surface, result))
        raise RuntimeError("Installed runtime TTY handoff failed with exit code 1.")

    monkeypatch.setattr(script_runtime, "handoff_to_installed_runtime", failed_handoff)
    monkeypatch.setattr(script_runtime, "_write_install_diagnostic_log", lambda *args, **kwargs: tmp_path / "install.log")
    monkeypatch.setattr(
        script_runtime,
        "_print_plain",
        lambda surface, payload, **kwargs: rendered.update(surface=surface, payload=payload),
    )

    assert script_runtime.main(["--surface", "windows", "--tty"]) == 1
    assert len(handoff_calls) == 1
    assert rendered["payload"]["error_code"] == "INSTALLED_RUNTIME_HANDOFF_FAILED"
    assert rendered["payload"]["failed_step"] == "runtime_tty_handoff"
    assert "Run the installed launcher directly" in rendered["payload"]["recovery_action"]


@pytest.mark.parametrize(
    ("keys", "reason", "code", "ok", "status"),
    [
        ([*"/exit", "ENTER"], "user_exit", 0, True, "ok"),
        (["ESC"], "user_exit", 0, True, "ok"),
    ],
)
def test_runtime_user_exit_codes(keys, reason, code, ok, status):
    from m32_bridge.installer.tty_app import run_tty_app

    result = {"tty_mode": "runtime", "ok": True, "status": "ok", "runtime_info": {}}
    final, _ = run_tty_app(
        "posix", result, dry_run=False, color=False, key_reader=iter(keys).__next__, stream=TTYBuffer(), size_provider=lambda: (80, 20)
    )
    assert final["runtime_exit_reason"] == reason
    assert final["runtime_exit_code"] == code
    assert final["ok"] is ok
    assert final["status"] == status


@pytest.mark.parametrize(
    ("error", "reason", "code", "status", "copy"),
    [
        (EOFError(), "input_failure", 1, "runtime_input_failed", "Reopen the Runtime Console"),
        (OSError("closed"), "input_failure", 1, "runtime_input_failed", "Reopen the Runtime Console"),
        (RuntimeError("closed"), "input_failure", 1, "runtime_input_failed", "Reopen the Runtime Console"),
        (KeyboardInterrupt(), "interrupted", 130, "interrupted", None),
    ],
)
def test_runtime_failure_exit_codes_restore_terminal(error, reason, code, status, copy):
    from m32_bridge.installer.tty_app import run_tty_app

    def fail():
        raise error

    stream = TTYBuffer()
    result = {"tty_mode": "runtime", "ok": True, "status": "ok", "runtime_info": {}}
    final, transcript = run_tty_app(
        "posix", result, dry_run=False, color=True, key_reader=fail, stream=stream, size_provider=lambda: (80, 20)
    )
    assert final["runtime_exit_reason"] == reason
    assert final["runtime_exit_code"] == code
    assert final["ok"] is False
    assert final["status"] == status
    if copy:
        assert copy in transcript
        assert "reopen the installer" not in transcript.lower()
    assert "\x1b[?7h" in stream.getvalue()


def test_run_runtime_tty_returns_actual_exit_code(monkeypatch):
    from m32_bridge.installer import tty_app
    from m32_bridge.runtime_preconditions import ConsolePrecondition

    monkeypatch.setattr(tty_app, "verify_runtime_import_provenance", lambda: {})
    monkeypatch.setattr(tty_app, "evaluate_console_precondition", lambda: ConsolePrecondition.setup_required())
    monkeypatch.setattr(tty_app, "run_tty_app", lambda *args, **kwargs: ({"runtime_exit_code": 130}, ""))
    assert tty_app.run_runtime_tty() == 130


def _installer_schema() -> dict:
    root = Path(__file__).resolve().parents[2]
    return json.loads(
        (
            root
            / "specs"
            / "003-cross-platform-installers-and-first-run-setup"
            / "contracts"
            / "installer-output.schema.json"
        ).read_text(encoding="utf-8")
    )


def _successful_install_payload(tmp_path):
    from m32_bridge.installer.runtime_manager import RuntimeManagerState
    from m32_bridge.installer.script_runtime import build_install_result, perform_apply_install

    uv_bin = tmp_path / "uv"
    uv_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    planned = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    return perform_apply_install("posix", planned, uv_bin=str(uv_bin))


def test_success_installer_output_validates_against_schema(tmp_path):
    payload = _successful_install_payload(tmp_path)
    Draft202012Validator(_installer_schema()).validate(payload)
    assert payload["verification_guidance"]["offered"] is True


def test_runtime_handoff_failure_output_validates_against_schema(tmp_path):
    from m32_bridge.installer.script_runtime import _controlled_install_failure

    success = _successful_install_payload(tmp_path)
    failure = _controlled_install_failure(
        "posix",
        success,
        error_code="INSTALLED_RUNTIME_HANDOFF_FAILED",
        failed_step="runtime_tty_handoff",
        message="The installed Runtime Console could not be started.",
        recovery_action="Run the installed launcher directly.",
        diagnostic_log_path=str(tmp_path / "logs" / "install.log"),
    )
    Draft202012Validator(_installer_schema()).validate(failure)
    assert failure["ok"] is False
    assert failure["error_code"] == "INSTALLED_RUNTIME_HANDOFF_FAILED"
