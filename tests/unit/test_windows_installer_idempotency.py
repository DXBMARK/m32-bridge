from __future__ import annotations

from pathlib import Path

from installer_test_helpers import isolated_install_home

from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target
from m32_bridge.installer.runtime_manager import RuntimeManagerState
from m32_bridge.installer.script_runtime import build_install_result, perform_apply_install
from m32_bridge.installer.state import determine_install_state


ROOT = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"


def _install_ps1_text() -> str:
    assert WINDOWS_INSTALLER.exists(), "T024/T027 must add Windows idempotency messaging to scripts/install.ps1"
    return WINDOWS_INSTALLER.read_text(encoding="utf-8")


def _windows_location(tmp_path: Path):
    home = isolated_install_home(tmp_path)
    target = installation_target(os_family="windows", shell_family="powershell")
    return default_install_location(target, local_app_data=home.windows_local_app_data)


def test_windows_install_state_model_covers_required_idempotency_states(tmp_path):
    location = _windows_location(tmp_path)

    cases = {
        "fresh_install": determine_install_state(location, app_exists=False, launcher_exists=False),
        "existing_install": determine_install_state(location, app_exists=False, launcher_exists=True),
        "repair": determine_install_state(location, app_exists=True, launcher_exists=False),
        "update": determine_install_state(
            location,
            app_exists=True,
            launcher_exists=True,
            current_version="0.1.0",
            target_version="0.2.0",
        ),
        "already_current": determine_install_state(
            location,
            app_exists=True,
            launcher_exists=True,
            current_version="0.2.0",
            target_version="0.2.0",
        ),
        "partial_failure": determine_install_state(location, partial_failure_marker=True),
    }

    for expected_status, state in cases.items():
        assert state.status == expected_status
        assert state.osc_writes_sent == 0
        assert state.hardware_verified is False
        assert state.production_live_ready is False


def test_windows_script_reports_all_idempotency_states_without_silent_success():
    text = _install_ps1_text().lower()

    for state in [
        "fresh_install",
        "existing_install",
        "repair",
        "update",
        "already_current",
        "partial_failure",
        "failed",
    ]:
        assert state in text
    assert "silent success" not in text
    assert "recovery" in text or "next step" in text


def test_windows_apply_materializes_app_without_forbidden_files(tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    result = build_install_result(
        surface="windows",
        platform="windows_powershell",
        dry_run=False,
        local_app_data=local_app_data,
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    applied = perform_apply_install("windows", result)
    app_path = Path(applied["app_path"])

    assert applied["ok"] is True
    assert (app_path / "pyproject.toml").is_file()
    assert (app_path / "uv.lock").is_file()
    assert (app_path / "src" / "m32_bridge").is_dir()
    assert not (app_path / ".git").exists()
    assert not (app_path / ".venv").exists()
    assert not any("__pycache__" in path.parts for path in app_path.rglob("*"))
    assert not (app_path / "tests").exists()


def test_windows_materialization_failure_is_not_success(monkeypatch, tmp_path):
    result = build_install_result(
        surface="windows",
        platform="windows_powershell",
        dry_run=False,
        local_app_data=tmp_path / "LocalAppData",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    def fail_materialize(*args, **kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr("m32_bridge.installer.script_runtime._materialize_app", fail_materialize)
    applied = perform_apply_install("windows", result)

    assert applied["ok"] is False
    assert applied["status"] in {"partial_failure", "failed"}
    assert applied["hardware_verified"] is False
    assert applied["production_live_ready"] is False
    assert applied["osc_writes_sent"] == 0
