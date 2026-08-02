from __future__ import annotations

import json
import os
from pathlib import Path

from m32_bridge import cli
from m32_bridge.installer import runtime_manager


def _ready_runtime() -> dict:
    return {
        "uv_detected": True,
        "uv_version": "uv 0.12.1",
        "uv_path": "/home/operator/.local/bin/uv",
        "managed_python_detected": True,
        "python_version": "3.13.14",
        "python_path": (
            "/home/operator/.m32-bridge/"
            "app/.venv/bin/python3"
        ),
        "python_source": "uv_managed",
        "system_python_version": "3.8.2",
        "system_python_path": "/usr/bin/python3",
        "system_python_used": False,
        "system_python_modified": False,
        "approved_minor": "3.13",
        "project_required_range": ">=3.11,<3.14",
    }


def _create_installation(
    tmp_path: Path,
) -> tuple[Path, Path]:
    app = tmp_path / "app"
    launcher = tmp_path / "bin" / "m32-bridge"

    app.mkdir(parents=True)
    launcher.parent.mkdir(parents=True)
    launcher.write_text(
        "#!/bin/sh\nexit 0\n",
        encoding="utf-8",
    )

    return app, launcher


def _patch_ready_runtime(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runtime_manager,
        "inspect_runtime",
        lambda *, environ=None: _ready_runtime(),
    )


def _patch_launcher_executable(
    monkeypatch,
) -> None:
    original_access = os.access

    def fake_access(path, mode):
        if mode == os.X_OK:
            return True
        return original_access(path, mode)

    monkeypatch.setattr(
        runtime_manager.os,
        "access",
        fake_access,
    )


def test_paths_are_discovered_from_supplied_environment(
    monkeypatch,
    tmp_path,
):
    app, launcher = _create_installation(tmp_path)
    _patch_ready_runtime(monkeypatch)
    _patch_launcher_executable(monkeypatch)

    payload = runtime_manager.local_runtime_diagnostics(
        environ={
            "M32_BRIDGE_APP_DIR": str(app),
            "M32_BRIDGE_LAUNCHER": str(launcher),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert payload["ok"] is True
    assert payload["healthy"] is True
    assert payload["status"] == "ok"
    assert payload["error_code"] is None

    assert payload["app_path"] == str(app.resolve())
    assert payload["launcher_path"] == str(
        launcher.resolve()
    )

    assert payload["app_files"] == "available"
    assert payload["app_path_status"] == "available"
    assert payload["launcher_file"] == "available"
    assert payload["launcher_path_status"] == "available"
    assert payload["launcher_executable"] is True

    assert payload["runtime_ready"] is True
    assert payload["installation_ready"] is True
    assert payload["path_visibility"] is False
    assert payload["required_actions"] == []

    assert payload["console_probe"] == "not_run"
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False


def test_explicit_paths_override_environment_paths(
    monkeypatch,
    tmp_path,
):
    app, launcher = _create_installation(tmp_path)
    _patch_ready_runtime(monkeypatch)
    _patch_launcher_executable(monkeypatch)

    payload = runtime_manager.local_runtime_diagnostics(
        environ={
            "M32_BRIDGE_APP_DIR": str(
                tmp_path / "wrong-app"
            ),
            "M32_BRIDGE_LAUNCHER": str(
                tmp_path / "wrong-launcher"
            ),
            "PATH": str(launcher.parent),
        },
        app_path=str(app),
        launcher_path=str(launcher),
    )

    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["app_path"] == str(app.resolve())
    assert payload["launcher_path"] == str(
        launcher.resolve()
    )
    assert payload["app_files"] == "available"
    assert payload["launcher_file"] == "available"
    assert payload["launcher_executable"] is True
    assert payload["path_visibility"] is True


def test_supplied_environment_does_not_read_global_path_values(
    monkeypatch,
    tmp_path,
):
    app, launcher = _create_installation(tmp_path)
    _patch_ready_runtime(monkeypatch)
    _patch_launcher_executable(monkeypatch)

    monkeypatch.setenv(
        "M32_BRIDGE_APP_DIR",
        str(app),
    )
    monkeypatch.setenv(
        "M32_BRIDGE_LAUNCHER",
        str(launcher),
    )

    payload = runtime_manager.local_runtime_diagnostics(
        environ={
            "PATH": "/usr/bin:/bin",
            "M32_BRIDGE_INSTALLED_RUNTIME": "1",
        },
    )

    assert payload["ok"] is False
    assert payload["healthy"] is False
    assert payload["status"] == "action_required"
    assert (
        payload["error_code"]
        == "RUNTIME_ACTION_REQUIRED"
    )

    assert payload["app_path"] is None
    assert payload["launcher_path"] is None
    assert payload["app_files"] == "not_found"
    assert payload["launcher_file"] == "not_found"
    assert payload["launcher_executable"] is False

    assert payload["console_probe"] == "not_run"
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_missing_installation_paths_are_not_healthy(
    monkeypatch,
    tmp_path,
):
    _patch_ready_runtime(monkeypatch)

    payload = runtime_manager.local_runtime_diagnostics(
        environ={
            "M32_BRIDGE_APP_DIR": str(
                tmp_path / "missing-app"
            ),
            "M32_BRIDGE_LAUNCHER": str(
                tmp_path / "missing-launcher"
            ),
            "PATH": "/usr/bin:/bin",
            "M32_BRIDGE_INSTALLED_RUNTIME": "1",
        },
    )

    assert payload["runtime_ready"] is True
    assert payload["installation_ready"] is False

    assert payload["ok"] is False
    assert payload["healthy"] is False
    assert payload["status"] == "action_required"
    assert (
        payload["error_code"]
        == "RUNTIME_ACTION_REQUIRED"
    )

    assert payload["app_files"] == "not_found"
    assert payload["launcher_file"] == "not_found"
    assert payload["launcher_executable"] is False
    assert payload["required_actions"]

    assert payload["console_probe"] == "not_run"
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_path_visibility_is_separate_from_launcher_health(
    monkeypatch,
    tmp_path,
):
    app, launcher = _create_installation(tmp_path)
    _patch_ready_runtime(monkeypatch)
    _patch_launcher_executable(monkeypatch)

    payload = runtime_manager.local_runtime_diagnostics(
        environ={
            "M32_BRIDGE_APP_DIR": str(app),
            "M32_BRIDGE_LAUNCHER": str(launcher),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert payload["path_visibility"] is False
    assert payload["launcher_executable"] is True
    assert payload["installation_ready"] is True
    assert payload["ok"] is True
    assert payload["status"] == "ok"


def test_doctor_runtime_cli_returns_nonzero_when_repair_is_required(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        runtime_manager,
        "local_runtime_diagnostics",
        lambda **kwargs: {
            "ok": False,
            "healthy": False,
            "status": "action_required",
            "error_code": "RUNTIME_ACTION_REQUIRED",
            "app_files": "not_found",
            "launcher_file": "not_found",
            "launcher_executable": False,
            "required_actions": [
                "Restore the installed application directory."
            ],
            "console_probe": "not_run",
            "network_scan": "not_run",
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        },
    )

    exit_code = cli.main(["doctor-runtime"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["status"] == "action_required"
    assert (
        payload["error_code"]
        == "RUNTIME_ACTION_REQUIRED"
    )
    assert payload["console_probe"] == "not_run"
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_source_checkout_runtime_does_not_require_installed_paths(
    monkeypatch,
):
    _patch_ready_runtime(monkeypatch)

    payload = runtime_manager.local_runtime_diagnostics(
        environ={
            "PATH": "/usr/bin:/bin",
        },
    )

    assert payload["execution_context"] == "source_checkout"
    assert payload["installed_runtime"] is False
    assert payload["installation_expected"] is False
    assert payload["installation_paths_ready"] is False
    assert payload["installation_ready"] is True

    assert payload["app_files"] == "not_found"
    assert payload["launcher_file"] == "not_found"
    assert payload["launcher_executable"] is False

    assert payload["runtime_ready"] is True
    assert payload["ok"] is True
    assert payload["healthy"] is True
    assert payload["status"] == "ok"
    assert payload["error_code"] is None
    assert payload["required_actions"] == []

    assert payload["console_probe"] == "not_run"
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0
