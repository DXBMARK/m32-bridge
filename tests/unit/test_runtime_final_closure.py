from __future__ import annotations

import io
import json
import os
import types
import urllib.error
from email.message import Message
from pathlib import Path

import pytest


class _TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def _runtime_result(tmp_path: Path) -> dict:
    app = tmp_path / ".m32-bridge" / "app"
    (app / ".venv").mkdir(parents=True, exist_ok=True)
    (app / "src" / "m32_bridge").mkdir(parents=True, exist_ok=True)
    (app / "pyproject.toml").write_text("[project]\nname='m32-mcp-bridge'\nversion='0.1.0'\n", encoding="utf-8")
    (app / "src" / "m32_bridge" / "__init__.py").write_text("", encoding="utf-8")
    launcher = tmp_path / ".local" / "bin" / "m32-bridge"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\nexec true\n", encoding="utf-8")
    launcher.chmod(0o755)
    return {
        "tty_mode": "runtime",
        "ok": True,
        "status": "ok",
        "app_path": str(app),
        "launcher_path": str(launcher),
        "platform": "linux",
        "architecture": "x86_64",
        "runtime_info": {
            "status": "ok",
            "application_runtime_ready": True,
            "uv_detected": True,
            "uv_path": "/opt/uv",
            "uv_version": "uv 0.10.0",
            "managed_python_version": "3.13.12",
            "python_path": "/opt/python3.13",
            "launcher": "uv run --frozen --no-build --no-sync",
        },
        "platform_info": {
            "os": "Linux",
            "version": "24.04",
            "kernel_build": "6.8",
            "architecture": "x86_64",
            "shell": "bash",
            "container_hint": "not_detected",
            "wsl": "not_detected",
        },
        "hardware_verified": False,
    }


def _metadata(result: dict, *, source: str = "github_release_or_archive", source_ref: str | None = "main") -> dict:
    from m32_bridge.installer.install_metadata import build_install_metadata

    source_url = None
    if source == "github_release_or_archive":
        source_url = "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz"
    elif source == "custom":
        source_url = "https://example.invalid/custom.zip"
    return build_install_metadata(
        "posix",
        {
            **result,
            "install_source": source,
            "source_ref": source_ref,
            "source_url": source_url,
            "target_version": "0.1.0",
        },
        installed_at="2026-08-02T00:00:00+00:00",
    )


def _write_metadata(result: dict, **kwargs) -> Path:
    from m32_bridge.installer.install_metadata import write_install_metadata

    return write_install_metadata(_metadata(result, **kwargs), app_path=result["app_path"])


def _planned_install(tmp_path: Path) -> dict:
    from m32_bridge.installer.runtime_manager import RuntimeManagerState
    from m32_bridge.installer.script_runtime import build_install_result

    return build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="present"),
        source_ref="main",
    )


def test_metadata_write_oserror_does_not_block_runtime_handoff(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    planned = _planned_install(tmp_path)
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *args, **kwargs: None)
    monkeypatch.setattr(script_runtime, "_resolve_uv_executable", lambda *args, **kwargs: "/opt/uv")
    monkeypatch.setattr(script_runtime, "write_install_metadata", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    applied = script_runtime.perform_apply_install("posix", planned, uv_bin="/opt/uv")
    assert applied["ok"] is True
    assert applied["runtime_info"]["application_runtime_ready"] is True
    assert applied["runtime_info"]["install_metadata_status"] == "write_failed"
    assert applied["runtime_handoff"]["installed_runtime"] is True
    assert applied.get("error_code") != "APP_MATERIALIZATION_FAILED"
    assert any("metadata" in item.lower() for item in applied["recommendations"])


def test_metadata_validation_failure_fails_closed_before_runtime_handoff(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    planned = _planned_install(tmp_path)
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *args, **kwargs: pytest.fail("materialization called"))
    monkeypatch.setattr(script_runtime, "_resolve_uv_executable", lambda *args, **kwargs: "/opt/uv")
    monkeypatch.setattr(script_runtime, "build_install_metadata", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad provenance")))
    applied = script_runtime.perform_apply_install("posix", planned, uv_bin="/opt/uv")
    assert applied["ok"] is False
    assert applied["error_code"] == "bad provenance"
    assert applied["runtime_info"]["application_runtime_ready"] is False
    assert "runtime_handoff" not in applied


def test_successful_metadata_write_reports_written(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    planned = _planned_install(tmp_path)
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *args, **kwargs: None)
    monkeypatch.setattr(script_runtime, "_resolve_uv_executable", lambda *args, **kwargs: "/opt/uv")
    applied = script_runtime.perform_apply_install("posix", planned, uv_bin="/opt/uv")
    path = Path(applied["app_path"]).parent / "install-metadata.json"
    assert applied["runtime_info"]["install_metadata_status"] == "written"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "1"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2"),
        ("installed_at", "not-a-time"),
        ("install_source", "unknown"),
        ("app_path", "relative/app"),
        ("launcher_path", "../bin/m32-bridge"),
        ("source_ref", "main\x1b[2J"),
    ],
)
def test_metadata_rejects_invalid_contract_values(tmp_path, field, value):
    from m32_bridge.installer.install_metadata import write_install_metadata

    result = _runtime_result(tmp_path)
    document = _metadata(result)
    document[field] = value
    with pytest.raises(ValueError):
        write_install_metadata(document, app_path=result["app_path"])


def test_metadata_source_ref_does_not_fallback_to_target_version(tmp_path):
    result = _runtime_result(tmp_path)
    document = _metadata(result, source="local_checkout", source_ref=None)
    assert document["source_ref"] == "not_available"
    assert document["application_version"] == "0.1.0"


@pytest.mark.parametrize(
    "url",
    [
        "https://user@github.com/DXBMARK/m32-bridge",
        "https://github.com/DXBMARK/m32-bridge?token=x",
        "https://github.com/DXBMARK/m32-bridge#fragment",
        "https://github.com:444/DXBMARK/m32-bridge",
    ],
)
def test_metadata_rejects_url_userinfo_query_fragment_and_nondefault_port(url):
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url(url) is False


def test_missing_metadata_status_refresh_performs_no_network(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    payload = build_runtime_status(_runtime_result(tmp_path), refresh=True, source_checker=lambda *_: pytest.fail("network"))
    assert payload["safety"]["internet_source_refresh"] == "not_run_metadata_missing"


def test_invalid_metadata_status_refresh_performs_no_network(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    path = Path(result["app_path"]).parent / "install-metadata.json"
    path.write_text("{bad", encoding="utf-8")
    payload = build_runtime_status(result, refresh=True, source_checker=lambda *_: pytest.fail("network"))
    assert payload["safety"]["internet_source_refresh"] == "not_run_metadata_invalid"


@pytest.mark.parametrize(
    ("source", "expected"),
    [("custom", "not_run_custom_source"), ("local_checkout", "not_run_local_source")],
)
def test_untrusted_source_status_refresh_performs_no_network(monkeypatch, tmp_path, source, expected):
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    _write_metadata(result, source=source, source_ref=None)
    payload = build_runtime_status(result, refresh=True, source_checker=lambda *_: pytest.fail("network"))
    assert payload["safety"]["internet_source_refresh"] == expected


def test_official_status_refresh_uses_exact_four_targets(tmp_path):
    from m32_bridge.installer.runtime_manager import OFFICIAL_RAW_INSTALLER_URLS, OFFICIAL_SOURCE_ARCHIVE_URLS
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    _write_metadata(result)
    calls = []
    build_runtime_status(result, refresh=True, source_checker=lambda url, timeout: calls.append(url) or "reachable")
    assert calls == [
        "https://github.com/",
        "https://github.com/DXBMARK/m32-bridge",
        OFFICIAL_RAW_INSTALLER_URLS["posix"],
        OFFICIAL_SOURCE_ARCHIVE_URLS["posix"],
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/DXBMARK/m32-bridge/issues",
        "https://github.com/DXBMARK/m32-bridge/tree/main",
        "https://github.com/DXBMARK/m32-bridge/../evil",
        "https://github.com/DXBMARK/m32-bridge/%2e%2e/evil",
        "https://127.0.0.1/DXBMARK/m32-bridge",
        "https://192.168.1.2/DXBMARK/m32-bridge",
    ],
)
def test_source_refresh_rejects_noncanonical_targets(url):
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url(url) is False


def test_source_refresh_revalidates_redirect_destination(monkeypatch):
    from m32_bridge.installer import runtime_status

    calls = []
    headers = Message()
    headers["Location"] = "http://127.0.0.1/steal"

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, io.BytesIO())

    monkeypatch.setattr(runtime_status.urllib.request, "build_opener", lambda *args: Opener())
    official = "https://github.com/DXBMARK/m32-bridge"
    assert runtime_status._bounded_https_status(official, 0.1, allowed_urls=frozenset({official})) == "redirect_rejected"
    assert calls == [official]


def test_status_healthy_is_top_level_ok(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    payload = build_runtime_status(_runtime_result(tmp_path))
    assert payload["snapshot_complete"] is True
    assert (payload["application_health"], payload["ok"], payload["status"]) == ("healthy", True, "ok")


def test_status_action_required_is_not_top_level_ok(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    Path(result["launcher_path"]).unlink()
    payload = build_runtime_status(result)
    assert (payload["application_health"], payload["ok"], payload["status"]) == ("action_required", False, "action_required")


def test_status_error_returns_nonzero(monkeypatch, tmp_path, capsys):
    from m32_bridge import cli

    result = _runtime_result(tmp_path)
    result["runtime_info"]["status"] = "error"
    monkeypatch.setenv("M32_BRIDGE_APP_DIR", result["app_path"])
    monkeypatch.setenv("M32_BRIDGE_LAUNCHER", result["launcher_path"])
    monkeypatch.setattr("m32_bridge.installer.runtime_status.local_runtime_diagnostics", lambda **kwargs: result["runtime_info"])
    assert cli.main(["status", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize("missing", ["app", "venv", "launcher"])
def test_missing_application_inputs_mark_action_required(tmp_path, missing):
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    if missing == "app":
        result["app_path"] = str(tmp_path / "missing")
    elif missing == "venv":
        Path(result["app_path"], ".venv").rmdir()
    else:
        Path(result["launcher_path"]).unlink()
    assert build_runtime_status(result)["application_health"] == "action_required"


def test_non_executable_posix_launcher_marks_action_required(tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    Path(result["launcher_path"]).chmod(0o644)
    assert build_runtime_status(result)["application"]["health_checks"]["launcher_executable"] == "not_executable"


def test_required_import_check_executes_real_imports(monkeypatch, tmp_path):
    from m32_bridge.installer import runtime_status

    calls = []
    original = runtime_status.importlib.import_module
    monkeypatch.setattr(runtime_status.importlib, "import_module", lambda name: calls.append(name) or original(name))
    runtime_status.build_runtime_status(_runtime_result(tmp_path))
    assert calls == ["yaml", "mcp", "pydantic", "m32_bridge"]


def test_failed_required_import_marks_action_required(monkeypatch, tmp_path):
    from m32_bridge.installer import runtime_status

    original = runtime_status.importlib.import_module
    monkeypatch.setattr(runtime_status.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError()) if name == "mcp" else original(name))
    payload = runtime_status.build_runtime_status(_runtime_result(tmp_path))
    assert payload["application_health"] == "action_required"
    assert payload["application"]["health_checks"]["required_import_details"]["mcp"]["status"] == "import_failed"


def test_bootstrap_import_provenance_is_rejected(monkeypatch, tmp_path):
    from m32_bridge.installer import runtime_status

    original = runtime_status.importlib.import_module
    monkeypatch.setattr(runtime_status.importlib, "import_module", lambda name: types.SimpleNamespace(__file__="/private/tmp/bootstrap/src/m32_bridge/__init__.py") if name == "m32_bridge" else original(name))
    payload = runtime_status.build_runtime_status(_runtime_result(tmp_path))
    assert payload["application_health"] == "action_required"
    assert payload["application"]["health_checks"]["import_provenance"] == "rejected_bootstrap"


def test_health_performs_no_network_or_console_probe(monkeypatch, tmp_path):
    from m32_bridge.installer import runtime_status

    monkeypatch.setattr(runtime_status, "_bounded_https_status", lambda *args, **kwargs: pytest.fail("network"))
    payload = runtime_status.build_runtime_health(_runtime_result(tmp_path))
    assert payload["safety"] == {"attempted_path": "not_attempted", "console_probe": "not_run", "network_scan": "not_run", "osc_writes_sent": 0}


def _configured_result(monkeypatch, tmp_path) -> tuple[dict, Path]:
    from m32_bridge.installer.runtime_status import record_console_result

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.write_text("host: 192.0.2.10\nport: 10023\ntarget_type: unknown\n", encoding="utf-8")
    record_console_result(result, {"connected": True, "attempted_path": "/info", "configured_host": "192.0.2.10", "configured_port": 10023, "config_path": str(config), "intended_target_type": "unknown", "latency_ms": 0})
    return result, config


def test_matching_endpoint_preserves_last_known_state(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    result, _ = _configured_result(monkeypatch, tmp_path)
    payload = build_runtime_status(result)
    assert payload["connection_state"] == "reachable"
    assert payload["console_connection"]["endpoint_verified"] is True
    assert payload["console_connection"]["last_latency_ms"] == 0


@pytest.mark.parametrize("change", ["host", "port", "path"])
def test_endpoint_change_clears_endpoint_verified(monkeypatch, tmp_path, change):
    from m32_bridge.installer.runtime_status import build_runtime_status

    result, config = _configured_result(monkeypatch, tmp_path)
    if change == "host":
        config.write_text("host: 192.0.2.11\nport: 10023\n", encoding="utf-8")
    elif change == "port":
        config.write_text("host: 192.0.2.10\nport: 10024\n", encoding="utf-8")
    else:
        alternate_home = tmp_path / "alternate-home"
        alternate = alternate_home / ".m32-bridge" / "runtime.yaml"
        alternate.parent.mkdir(parents=True)
        alternate.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(alternate_home))
    payload = build_runtime_status(result)
    assert payload["connection_state"] == "not_checked"
    assert payload["operational_state"] == "console_not_checked"
    assert payload["console_connection"]["endpoint_verified"] is False


@pytest.mark.parametrize(
    ("malicious", "forbidden"),
    [
        ("safe\x1b[2Jbad", "\x1b"),
        ("safe\x1b]0;owned\x07bad", "owned"),
        ("one\ntwo\rthree\tfour", "\n"),
        ("a\x00b\x85c", "\x00"),
    ],
)
def test_external_terminal_sequences_are_removed(malicious, forbidden):
    from m32_bridge.installer.display_safety import sanitize_display_value

    rendered = sanitize_display_value(malicious)
    assert forbidden not in rendered
    assert "\n" not in rendered and "\r" not in rendered and "\t" not in rendered


def test_long_external_value_is_bounded():
    from m32_bridge.installer.display_safety import sanitize_display_value

    rendered = sanitize_display_value("x" * 1000, max_length=64)
    assert len(rendered) == 64 and rendered.endswith("…")


def test_get_info_device_name_cannot_control_terminal():
    from m32_bridge.installer.tty_app import render_get_info_panel

    text = render_get_info_panel({"connected": True, "attempted_path": "/info", "data": {"name": "FOH\x1b[2J\nSAFETY"}})
    assert "\x1b[2J" not in text
    assert text.count("SAFETY") == 2  # sanitized value plus the real section, never a new row


def test_metadata_source_ref_and_config_label_cannot_control_terminal(tmp_path):
    from m32_bridge.installer.tty_app import render_runtime_status_panel
    from m32_bridge.installer.runtime_status import build_runtime_status

    payload = build_runtime_status(_runtime_result(tmp_path))
    payload["installation_source"]["source_ref"] = "main\x1b]0;owned\x07"
    payload["console_configuration"]["label"] = "FOH\nFAKE SECTION"
    text = render_runtime_status_panel(payload)
    assert "\x1b" not in text and "\nFAKE SECTION" not in text and "owned" not in text


def test_runtime_mode_never_calls_parse_installer_command(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setattr(tty_app, "parse_installer_command", lambda command: pytest.fail("legacy parser"))
    output, stop = tty_app.execute_installer_command("/status", _runtime_result(tmp_path))
    assert "RUNTIME STATUS" in output and stop is False


def test_typed_status_refresh_uses_runtime_status_refresh(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    calls = []
    monkeypatch.setattr(tty_app, "build_runtime_status", lambda result, refresh=False: calls.append(refresh) or {"marker": True})
    monkeypatch.setattr(tty_app, "render_runtime_status_panel", lambda payload, **kwargs: "STATUS")
    assert tty_app.dispatch_runtime_command("/status refresh", _runtime_result(tmp_path)) == ("STATUS", False)
    assert calls == [True]


def test_picker_and_typed_status_use_same_handler_and_view():
    from m32_bridge.installer.runtime_status import RUNTIME_COMMAND_REGISTRY
    from m32_bridge.installer.tty_app import RUNTIME_SLASH_COMMANDS, _view_for_command

    assert any(item["cmd"] == "/status" for item in RUNTIME_SLASH_COMMANDS)
    assert RUNTIME_COMMAND_REGISTRY["/status"].handler_id == "runtime_status"
    assert _view_for_command("/status") == RUNTIME_COMMAND_REGISTRY["/status"].view == "status"


def test_unknown_runtime_command_is_contained(tmp_path):
    from m32_bridge.installer.tty_app import dispatch_runtime_command

    output, stop = dispatch_runtime_command("/does-not-exist; rm", _runtime_result(tmp_path))
    assert output.startswith("Unknown command") and stop is False


@pytest.mark.parametrize(("width", "height"), [(80, 24), (60, 20)])
def test_dashboard_critical_fields_visible(monkeypatch, tmp_path, width, height):
    from m32_bridge.installer.tty_app import render_full_screen, strip_ansi

    monkeypatch.setenv("HOME", str(tmp_path))
    text = strip_ansi(render_full_screen("posix", _runtime_result(tmp_path), dry_run=False, color=False, width=width, height=height))
    for value in ("X32-Bridge MCP", "Linux", "x86_64", "3.13.12", "Configuration state", "Connection state", "Operational state", "OSC writes", "Network scan"):
        assert value in text
    assert "not_run" in text and "RUNTIME READY" not in text


def test_container_and_wsl_are_rendered_independently(tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status
    from m32_bridge.installer.tty_app import render_runtime_status_panel

    result = _runtime_result(tmp_path)
    result["platform_info"].update(container_hint="not_detected", wsl="detected")
    text = render_runtime_status_panel(build_runtime_status(result))
    assert "Container" in text and "WSL" in text and "detected" in text


def test_zero_latency_is_preserved():
    from m32_bridge.installer.tty_app import render_get_info_panel

    text = render_get_info_panel({"connected": True, "latency_ms": 0, "latency": 55, "attempted_path": "/info"})
    assert "Latency" in text and ": 0" in text and "55" not in text


def test_all_real_runtime_handlers_execute_without_fake_handler_map(monkeypatch, tmp_path):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    monkeypatch.setattr(tty_app, "_load_console_command_handlers", lambda: (
        lambda **kwargs: {"connected": True, "status": "ok", "attempted_path": "/info", "latency_ms": 0, "data": {}},
        lambda **kwargs: {"connected": True, "status": "ok", "attempted_path": "/info", "latency_ms": 0, "classification": "CONNECTED_UNVERIFIED", "data": {}},
    ))
    result = _runtime_result(tmp_path)
    outputs = {}
    for command in tty_app.RUNTIME_COMMAND_REGISTRY:
        if command == "/setup":
            output, stop = tty_app.dispatch_runtime_command(command, result)
        else:
            output, stop = tty_app.dispatch_runtime_command(command, result, width=80)
        outputs[command] = output
        assert "Traceback" not in output and not output.lstrip().startswith("{")
        assert stop is (command == "/exit")
    assert "RUNTIME CONSOLE HELP" in outputs["/help"]
    assert "RUNTIME STATUS" in outputs["/status"]
    assert "HEALTH" in outputs["/health"]
    assert "CONSOLE INFORMATION" in outputs["/get-info"]
    assert "DEVICE VERIFICATION" in outputs["/verify-device"]


@pytest.mark.parametrize("command", ["/help", "/status", "/status refresh", "/health", "/setup", "/get-info", "/verify-device", "/doctor-runtime", "/mcp-config", "/contact", "/clear", "/exit"])
def test_all_real_runtime_handlers_execute_through_tty_loop(monkeypatch, tmp_path, command):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    monkeypatch.setattr(tty_app, "_load_console_command_handlers", lambda: (
        lambda **kwargs: {"connected": True, "status": "ok", "attempted_path": "/info", "latency_ms": 0, "data": {}},
        lambda **kwargs: {"connected": True, "status": "ok", "attempted_path": "/info", "latency_ms": 0, "classification": "CONNECTED_UNVERIFIED", "data": {}},
    ))
    if command == "/exit":
        keys = [*command, "ENTER"]
    elif command in {"/setup", "/clear"}:
        keys = [*command, "ENTER", "ESC", *"/exit", "ENTER"]
    else:
        keys = [*command, "ENTER", "ESC", *"/exit", "ENTER"]
    final, transcript = tty_app.run_tty_app(
        "posix",
        result,
        dry_run=False,
        color=False,
        key_reader=iter(keys).__next__,
        stream=_TTYBuffer(),
        size_provider=lambda: (80, 24),
    )
    handler_id = tty_app.RUNTIME_COMMAND_REGISTRY[command].handler_id
    assert handler_id in final.get("_runtime_handler_trace", [])
    assert "Traceback" not in transcript and "Unknown command" not in transcript
    assert final["runtime_exit_code"] == 0


@pytest.mark.parametrize("command", ["/help", "/status", "/status refresh", "/health", "/doctor-runtime", "/mcp-config", "/get-info", "/verify-device"])
def test_actual_runtime_panels_scroll_to_final_line(monkeypatch, tmp_path, command):
    from m32_bridge.installer import tty_app

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    monkeypatch.setattr(tty_app, "_load_console_command_handlers", lambda: (
        lambda **kwargs: {"connected": True, "status": "ok", "attempted_path": "/info", "latency_ms": 0, "data": {}},
        lambda **kwargs: {"connected": True, "status": "ok", "attempted_path": "/info", "latency_ms": 0, "classification": "CONNECTED_UNVERIFIED", "data": {}},
    ))
    result = _runtime_result(tmp_path)
    panel, _ = tty_app.dispatch_runtime_command(command, result, width=80)
    lines = panel.splitlines()
    capacity = 8
    offset = max(len(lines) - capacity, 0)
    window, footer = tty_app._panel_window(lines, offset, capacity, view=tty_app._view_for_command(command))
    assert window[-1] == lines[-1]
    if len(lines) > capacity:
        assert footer.startswith("End of ")


def test_pinned_commit_archive_is_official_posix(tmp_path):
    result = _runtime_result(tmp_path)
    document = __import__("m32_bridge.installer.install_metadata", fromlist=["build_install_metadata"]).build_install_metadata(
        "posix",
        {**result, "install_source": "github_release_or_archive", "source_ref": "81bd994", "source_url": "https://github.com/DXBMARK/m32-bridge/archive/81bd994.tar.gz", "target_version": "0.1.0"},
    )
    assert document["install_source"] == "github_release_or_archive"
    assert document["source_ref"] == "81bd994"
    assert document["source_archive_url"].endswith("/archive/81bd994.tar.gz")
    assert document["raw_installer_url"].endswith("/81bd994/scripts/install.sh")
    assert "source_url_status" not in document


def test_pinned_commit_archive_is_official_windows(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata

    result = {
        **_runtime_result(tmp_path),
        "platform": "windows_powershell",
        "app_path": str(tmp_path / "Local" / "M32Bridge" / "app"),
        "launcher_path": str(tmp_path / "Local" / "M32Bridge" / "bin" / "m32-bridge.cmd"),
        "install_source": "github_release_or_archive",
        "source_ref": "81bd994",
        "source_url": "https://github.com/DXBMARK/m32-bridge/archive/81bd994.zip",
    }
    windows_app = Path(str(result["app_path"]))
    windows_app.mkdir(parents=True, exist_ok=True)
    (windows_app / "pyproject.toml").write_text("[project]\nname='m32-mcp-bridge'\nversion='0.1.0'\n", encoding="utf-8")
    document = build_install_metadata("windows", result)
    assert document["source_archive_url"].endswith("/archive/81bd994.zip")
    assert document["raw_installer_url"].endswith("/81bd994/scripts/install.ps1")


def test_pinned_raw_installer_is_official(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata

    result = _runtime_result(tmp_path)
    document = build_install_metadata("posix", {**result, "install_source": "github_raw", "source_ref": "81bd994", "source_url": "https://raw.githubusercontent.com/DXBMARK/m32-bridge/81bd994/scripts/install.sh"})
    assert document["install_source"] == "github_raw"
    assert document["raw_installer_url"].endswith("/81bd994/scripts/install.sh")
    assert document["source_archive_url"].endswith("/archive/81bd994.tar.gz")


def test_pinned_source_url_must_match_source_ref(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata

    result = _runtime_result(tmp_path)
    document = build_install_metadata("posix", {**result, "install_source": "github_release_or_archive", "source_ref": "81bd994", "source_url": "https://github.com/DXBMARK/m32-bridge/archive/abcdef1.tar.gz"})
    assert document["install_source"] == "custom"
    assert document["source_url_status"] == "not_persisted"
    assert "source_archive_url" not in document


def test_short_commit_minimum_seven_hex_supported():
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/abcdef1.tar.gz") is True
    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/0123456789abcdef0123456789abcdef01234567.tar.gz") is True


def test_non_hex_commit_rejected():
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/abcdeg1.tar.gz") is False


def test_commit_with_slash_rejected():
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/abc/def1.tar.gz") is False


def test_commit_with_query_or_fragment_rejected():
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/abcdef1.tar.gz?x=1") is False
    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/abcdef1.tar.gz#x") is False


def test_commit_with_percent_encoding_rejected():
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/%61bcdef1.tar.gz") is False


def test_commit_with_control_character_rejected():
    from m32_bridge.installer.install_metadata import is_official_source_url

    assert is_official_source_url("https://github.com/DXBMARK/m32-bridge/archive/abcdef1\x1b.tar.gz") is False


def test_live_install_style_metadata_is_not_custom(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata

    result = _runtime_result(tmp_path)
    document = build_install_metadata("posix", {**result, "install_source": "github_release_or_archive", "source_ref": "81bd994", "source_url": "https://github.com/DXBMARK/m32-bridge/archive/81bd994.tar.gz"})
    assert document["install_source"] != "custom"


def test_pinned_metadata_status_refresh_uses_exact_four_targets(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    document = build_install_metadata("posix", {**result, "install_source": "github_release_or_archive", "source_ref": "81bd994", "source_url": "https://github.com/DXBMARK/m32-bridge/archive/81bd994.tar.gz"})
    write_install_metadata(document, app_path=result["app_path"])
    calls = []
    payload = build_runtime_status(result, refresh=True, source_checker=lambda url, timeout: calls.append(url) or "reachable")
    assert calls == [
        "https://github.com/",
        "https://github.com/DXBMARK/m32-bridge",
        "https://raw.githubusercontent.com/DXBMARK/m32-bridge/81bd994/scripts/install.sh",
        "https://github.com/DXBMARK/m32-bridge/archive/81bd994.tar.gz",
    ]
    assert payload["safety"]["console_probe"] == "not_run"


def _redirect_result(
    monkeypatch,
    destination: str,
    *,
    initial: str = "https://github.com/DXBMARK/m32-bridge/archive/81bd994.tar.gz",
    allowed_redirect: str = "https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/81bd994",
) -> tuple[str, list[str]]:
    from m32_bridge.installer import runtime_status

    calls = []
    headers = Message()
    headers["Location"] = destination

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, io.BytesIO())
            return Response()

    monkeypatch.setattr(runtime_status.urllib.request, "build_opener", lambda *args: Opener())
    status = runtime_status._bounded_https_status(
        initial,
        0.1,
        initial_allowed_urls=frozenset({initial}),
        redirect_allowed_urls=frozenset({allowed_redirect}),
    )
    return status, calls


def test_pinned_archive_redirect_to_matching_codeload_is_allowed(monkeypatch):
    status, calls = _redirect_result(monkeypatch, "https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/81bd994")
    assert status == "reachable" and len(calls) == 2


def test_pinned_archive_redirect_to_different_commit_is_rejected(monkeypatch):
    status, calls = _redirect_result(monkeypatch, "https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/abcdef1")
    assert status == "redirect_rejected" and len(calls) == 1


def test_pinned_archive_redirect_to_different_repository_is_rejected(monkeypatch):
    status, calls = _redirect_result(monkeypatch, "https://codeload.github.com/OTHER/m32-bridge/tar.gz/81bd994")
    assert status == "redirect_rejected" and len(calls) == 1


def test_pinned_archive_redirect_to_private_host_is_rejected(monkeypatch):
    status, calls = _redirect_result(monkeypatch, "http://127.0.0.1/archive/81bd994")
    assert status == "redirect_rejected" and len(calls) == 1


def test_main_source_behavior_remains_supported(tmp_path):
    document = _metadata(_runtime_result(tmp_path), source_ref="main")
    assert document["install_source"] == "github_release_or_archive"
    assert document["source_archive_url"].endswith("/archive/refs/heads/main.tar.gz")
    assert document["raw_installer_url"].endswith("/main/scripts/install.sh")


def test_main_archive_matching_codeload_redirect_remains_supported(monkeypatch):
    initial = "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz"
    redirect = "https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/refs/heads/main"
    status, calls = _redirect_result(monkeypatch, redirect, initial=initial, allowed_redirect=redirect)
    assert status == "reachable" and calls == [initial, redirect]


def test_custom_source_still_performs_no_refresh(tmp_path):
    from m32_bridge.installer.install_metadata import write_install_metadata
    from m32_bridge.installer.runtime_status import build_runtime_status

    result = _runtime_result(tmp_path)
    write_install_metadata(_metadata(result, source="custom", source_ref=None), app_path=result["app_path"])
    payload = build_runtime_status(result, refresh=True, source_checker=lambda *_: pytest.fail("custom source contacted"))
    assert payload["safety"]["internet_source_refresh"] == "not_run_custom_source"
