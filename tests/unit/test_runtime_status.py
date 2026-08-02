from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest


def _runtime_result(tmp_path: Path) -> dict:
    app = tmp_path / ".m32-bridge" / "app"
    launcher = tmp_path / ".local" / "bin" / "m32-bridge"
    app.mkdir(parents=True, exist_ok=True)
    (app / ".venv").mkdir()
    (app / "src" / "m32_bridge").mkdir(parents=True)
    (app / "pyproject.toml").write_text("[project]\nname='m32-mcp-bridge'\nversion='0.1.0'\n", encoding="utf-8")
    (app / "src" / "m32_bridge" / "__init__.py").write_text("", encoding="utf-8")
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    return {
        "tty_mode": "runtime",
        "ok": True,
        "app_path": str(app),
        "launcher_path": str(launcher),
        "runtime_info": {
            "status": "ok",
            "uv_detected": True,
            "uv_version": "uv 0.8.0",
            "uv_path": "/opt/uv",
            "managed_python_version": "3.13.14",
            "python_version": "3.13.14",
            "python_path": "/opt/python3.13",
            "python_source": "uv_managed",
            "approved_minor": "3.13",
            "project_required_range": ">=3.11,<3.14",
            "system_python_version": "3.12.0",
            "system_python_path": "/usr/bin/python3",
        },
        "platform_info": {
            "os": "Linux",
            "version": "Ubuntu 24.04",
            "kernel_build": "6.8.0",
            "architecture": "x86_64",
            "shell": "bash",
            "container_hint": "none",
        },
        "console_connection_status": "not_checked",
        "hardware_verified": False,
    }


def _write_metadata(tmp_path: Path, result: dict, *, source_ref: str = "81bd994") -> Path:
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata

    planned = {
        **result,
        "target_version": "0.1.0",
        "source_ref": source_ref,
        "install_source": "github_release_or_archive",
        "source_url": f"https://github.com/DXBMARK/m32-bridge/archive/{source_ref}.tar.gz" if len(source_ref) >= 7 and all(character in "0123456789abcdefABCDEF" for character in source_ref) else "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz",
        "platform": "linux",
        "architecture": "x86_64",
    }
    metadata = build_install_metadata("posix", planned, installed_at="2026-08-02T00:00:00+00:00")
    return write_install_metadata(metadata, app_path=Path(result["app_path"]))


def test_install_metadata_written_atomically(tmp_path):
    from m32_bridge.installer.install_metadata import read_install_metadata

    result = _runtime_result(tmp_path)
    path = _write_metadata(tmp_path, result)
    assert path == Path(result["app_path"]).parent / "install-metadata.json"
    assert read_install_metadata(path)["status"] == "metadata_valid"
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_install_metadata_contains_source_ref(tmp_path):
    from m32_bridge.installer.install_metadata import read_install_metadata

    result = _runtime_result(tmp_path)
    path = _write_metadata(tmp_path, result, source_ref="abcdef1")
    assert read_install_metadata(path)["data"]["source_ref"] == "abcdef1"


def test_successful_apply_persists_install_metadata(monkeypatch, tmp_path):
    from m32_bridge.installer.install_metadata import install_metadata_path, read_install_metadata
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
        install_source="github_commit_archive",
        source_url=f"https://github.com/DXBMARK/m32-bridge/archive/{'a' * 40}.tar.gz",
        source_ref="a" * 40,
        source_commit="a" * 40,
    )
    applied = perform_apply_install("posix", planned, uv_bin=str(uv_bin))
    path = install_metadata_path(app_path=applied["app_path"])
    loaded = read_install_metadata(path)
    assert applied["ok"] is True
    assert loaded["status"] == "metadata_valid"
    assert loaded["data"]["source_ref"] == "a" * 40


def test_install_metadata_cannot_escape_install_root(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata

    result = _runtime_result(tmp_path)
    metadata = build_install_metadata("posix", result)
    with pytest.raises(ValueError, match="install root"):
        write_install_metadata(metadata, app_path=result["app_path"], path=tmp_path / "outside.json")


def test_install_metadata_redacts_or_rejects_url_credentials(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata

    result = _runtime_result(tmp_path) | {
        "source_url": "https://user:secret@github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        "install_source": "github_release_or_archive",
    }
    metadata = build_install_metadata("posix", result)
    assert metadata["install_source"] == "custom"
    assert metadata["source_url_status"] == "not_persisted"
    assert "source_archive_url" not in metadata
    assert "secret" not in json.dumps(metadata)


def test_local_install_metadata_does_not_invent_repository_provenance(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata

    metadata = build_install_metadata("posix", _runtime_result(tmp_path) | {"install_source": "local_checkout"})
    assert metadata["install_source"] == "local_checkout"
    assert "repository_url" not in metadata
    assert "source_archive_url" not in metadata


def test_runtime_survives_missing_install_metadata(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    payload = build_runtime_status(_runtime_result(tmp_path))
    assert payload["application"]["install_metadata_status"] == "metadata_missing"
    assert payload["application_health"] == "healthy"


def test_runtime_survives_malformed_install_metadata(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    path = Path(result["app_path"]).parent / "install-metadata.json"
    path.write_text("{broken", encoding="utf-8")
    payload = build_runtime_status(result)
    assert payload["application"]["install_metadata_status"] == "metadata_invalid"
    assert payload["application_health"] == "healthy"


def test_runtime_status_contains_application_platform_python_source_console_safety(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    _write_metadata(tmp_path, result)
    payload = build_runtime_status(result)
    for key in ("application", "platform", "python_runtime", "installation_source", "source_connectivity", "console_configuration", "console_connection", "safety"):
        assert key in payload
    assert payload["installation_source"]["source_ref"] == "81bd994"
    assert payload["safety"]["network_scan"] == "not_run"
    assert payload["safety"]["osc_writes_sent"] == 0


def test_runtime_status_has_no_installer_branding(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status
    from m32_bridge.installer.tty_app import render_runtime_status_panel

    monkeypatch.setenv("HOME", str(tmp_path))
    text = render_runtime_status_panel(build_runtime_status(_runtime_result(tmp_path)))
    assert "RUNTIME STATUS" in text
    assert "INSTALLER STATUS" not in text


def test_runtime_status_does_not_refresh_network_by_default(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    payload = build_runtime_status(
        _runtime_result(tmp_path),
        refresh=False,
        source_checker=lambda *_: pytest.fail("source refresh ran"),
    )
    assert payload["source_connectivity"]["github_repository"] == "not_checked"
    assert payload["safety"]["internet_source_refresh"] == "not_run"


def test_runtime_status_refresh_checks_only_official_github_sources(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    _write_metadata(tmp_path, result)
    calls: list[str] = []
    payload = build_runtime_status(
        result,
        refresh=True,
        source_checker=lambda url, timeout: calls.append(url) or "reachable",
    )
    assert len(calls) == 4
    assert calls[0] == "https://github.com/"
    assert all(url.startswith(("https://github.com/", "https://raw.githubusercontent.com/DXBMARK/m32-bridge/")) for url in calls)
    assert not any("localhost" in url or "192.168." in url for url in calls)
    assert payload["safety"]["internet_source_refresh"] == "run"
    assert payload["safety"]["console_probe"] == "not_run"


def test_runtime_status_refresh_rejects_custom_or_private_urls(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path) | {"install_source": "custom", "source_url": "http://192.168.1.5/source.zip"}
    payload = build_runtime_status(
        result,
        refresh=True,
        source_checker=lambda *_: pytest.fail("custom source contacted"),
    )
    assert payload["source_connectivity"]["github_repository"] == "metadata_missing"
    assert payload["safety"]["internet_source_refresh"] == "not_run_metadata_missing"


def test_runtime_status_refresh_does_not_probe_console(monkeypatch, tmp_path):
    from m32_bridge.installer import runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    monkeypatch.setattr(runtime_status, "record_console_result", lambda *_: pytest.fail("console result updated"))
    payload = runtime_status.build_runtime_status(result, refresh=True, source_checker=lambda *_: "reachable")
    assert payload["console_connection"]["last_attempted_path"] == "not_attempted"


def test_health_and_status_outputs_are_not_identical(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_health, build_runtime_status
    from m32_bridge.installer.tty_app import render_runtime_health_panel, render_runtime_status_panel

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    health = render_runtime_health_panel(build_runtime_health(result))
    status = render_runtime_status_panel(build_runtime_status(result))
    assert health != status
    assert "SOURCE CONNECTIVITY" not in health
    assert "SOURCE CONNECTIVITY" in status


def test_dashboard_contains_os_arch_version_and_source_ref(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status
    from m32_bridge.installer.tty_app import render_full_screen, strip_ansi

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    _write_metadata(tmp_path, result)
    build_runtime_status(result)
    text = strip_ansi(render_full_screen("posix", result, dry_run=False, color=False, width=120, height=32))
    for value in ("Linux", "Ubuntu 24.04", "x86_64", "bash", "81bd994", "uv 0.8.0", "3.13.14"):
        assert value in text


def test_dashboard_distinguishes_config_valid_from_connection_reachable(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    payload = build_runtime_status(_runtime_result(tmp_path))
    assert payload["configuration_state"] == "valid"
    assert payload["connection_state"] == "not_checked"
    assert payload["operational_state"] == "console_not_checked"


def test_runtime_dependency_failure_is_not_hidden_by_console_state(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".m32-bridge" / "runtime.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("host: 192.0.2.10\nport: 10023\n", encoding="utf-8")
    result = _runtime_result(tmp_path)
    result["runtime_info"]["status"] = "action_required"
    result["console_connection_status"] = "reachable"
    payload = build_runtime_status(result)
    assert payload["application_health"] == "action_required"
    assert payload["operational_state"] == "console_not_checked"


@pytest.mark.parametrize(
    ("application_health", "operational_state", "expected"),
    [
        ("healthy", "setup_required", "RUNTIME HEALTHY · SETUP REQUIRED"),
        ("healthy", "console_not_checked", "RUNTIME HEALTHY · CONSOLE NOT CHECKED"),
        ("healthy", "console_unreachable", "RUNTIME HEALTHY · CONSOLE UNREACHABLE"),
        ("healthy", "console_connected", "RUNTIME HEALTHY · CONSOLE CONNECTED"),
        ("healthy", "config_invalid", "CONFIG INVALID · RUN /setup"),
        ("action_required", "console_connected", "RUNTIME ACTION REQUIRED"),
    ],
)
def test_footer_semantic_states(application_health, operational_state, expected):
    from m32_bridge.installer.tty_app import render_footer_status

    footer = render_footer_status(
        {"tty_mode": "runtime", "application_health": application_health, "operational_state": operational_state},
        color=False,
    )
    assert expected in footer
    if operational_state == "console_unreachable":
        assert "RUNTIME READY" not in footer


def test_cli_status_and_tty_status_share_status_builder():
    from m32_bridge.installer import runtime_status, tty_app

    assert tty_app.build_runtime_status is runtime_status.build_runtime_status


def test_cli_status_refresh_is_explicit(monkeypatch, tmp_path, capsys):
    from m32_bridge import cli
    from m32_bridge.installer import runtime_status

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    _write_metadata(tmp_path, result)
    monkeypatch.setenv("M32_BRIDGE_APP_DIR", result["app_path"])
    monkeypatch.setenv("M32_BRIDGE_LAUNCHER", result["launcher_path"])
    calls: list[str] = []
    monkeypatch.setattr(runtime_status, "_bounded_https_status", lambda url, timeout, **kwargs: calls.append(url) or "reachable")
    assert cli.main(["status", "--json"]) == 0
    assert calls == []
    capsys.readouterr()
    assert cli.main(["status", "--refresh", "--json"]) == 0
    assert len(calls) == 4


def test_cli_status_plain_and_json_are_distinct(monkeypatch, tmp_path, capsys):
    from m32_bridge import cli

    monkeypatch.setenv("HOME", str(tmp_path))
    result = _runtime_result(tmp_path)
    monkeypatch.setenv("M32_BRIDGE_APP_DIR", result["app_path"])
    monkeypatch.setenv("M32_BRIDGE_LAUNCHER", result["launcher_path"])
    assert cli.main(["status"]) == 0
    plain = capsys.readouterr().out
    assert plain.startswith("RUNTIME STATUS")
    assert not plain.lstrip().startswith("{")
    assert cli.main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["safety"]["console_probe"] == "not_run"
