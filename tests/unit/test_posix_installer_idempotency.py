from __future__ import annotations

from pathlib import Path

from installer_test_helpers import isolated_install_home

from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target
from m32_bridge.installer.runtime_manager import RuntimeManagerState
from m32_bridge.installer.script_runtime import build_install_result, perform_apply_install
from m32_bridge.installer.state import determine_install_state


ROOT = Path(__file__).resolve().parents[2]
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"


def _install_sh_text() -> str:
    assert POSIX_INSTALLER.exists(), "T022/T027 must add POSIX idempotency messaging to scripts/install.sh"
    return POSIX_INSTALLER.read_text(encoding="utf-8")


def _posix_location(tmp_path: Path):
    home = isolated_install_home(tmp_path)
    target = installation_target(os_family="linux", shell_family="posix")
    return default_install_location(target, home=home.posix_home)


def test_posix_install_state_model_covers_required_idempotency_states(tmp_path):
    location = _posix_location(tmp_path)

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


def test_posix_script_reports_all_idempotency_states_without_silent_success():
    text = _install_sh_text().lower()

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


def test_posix_apply_materializes_app_without_forbidden_files(tmp_path):
    home = tmp_path / "home" / "operator"
    uv_bin = tmp_path / "runtime" / "uv"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=home,
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    applied = perform_apply_install("posix", result, uv_bin=str(uv_bin))
    app_path = Path(applied["app_path"])

    assert applied["ok"] is True
    assert applied["hardware_verified"] is False
    assert applied["production_live_ready"] is False
    assert applied["osc_writes_sent"] == 0
    assert (app_path / "pyproject.toml").is_file()
    assert (app_path / "uv.lock").is_file()
    assert (app_path / "src" / "m32_bridge").is_dir()
    assert not (app_path / ".git").exists()
    assert not (app_path / ".venv").exists()
    assert not any("__pycache__" in path.parts for path in app_path.rglob("*"))
    assert not (app_path / "tests").exists()
    assert not any(path.name in {".env", ".env.local", "config.local.yaml"} for path in app_path.rglob("*"))


def test_posix_rerun_preserves_user_config_and_does_not_destructively_overwrite(tmp_path):
    home = tmp_path / "home" / "operator"
    uv_bin = tmp_path / "runtime" / "uv"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=home,
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    first = perform_apply_install("posix", result, uv_bin=str(uv_bin))
    config = Path(first["install_root"]) / "config.yaml"
    config.write_text("host: 192.0.2.10\n", encoding="utf-8")

    rerun = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=home,
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    second = perform_apply_install("posix", rerun, uv_bin=str(uv_bin))

    assert second["ok"] is True
    assert config.read_text(encoding="utf-8") == "host: 192.0.2.10\n"


def test_posix_materialization_failure_is_not_success(monkeypatch, tmp_path):
    home = tmp_path / "home" / "operator"
    uv_bin = tmp_path / "runtime" / "uv"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=home,
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    def fail_materialize(*args, **kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr("m32_bridge.installer.script_runtime._materialize_app", fail_materialize)
    applied = perform_apply_install("posix", result, uv_bin=str(uv_bin))

    assert applied["ok"] is False
    assert applied["status"] in {"partial_failure", "failed"}
    assert applied["hardware_verified"] is False
    assert applied["production_live_ready"] is False
    assert applied["osc_writes_sent"] == 0
