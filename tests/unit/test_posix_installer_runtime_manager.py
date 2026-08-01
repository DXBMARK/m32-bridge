from __future__ import annotations

from pathlib import Path

from m32_bridge.installer import script_runtime
from m32_bridge.installer.runtime_manager import RuntimeManagerState, detect_uv_status


ROOT = Path(__file__).resolve().parents[2]
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"


def _install_sh_text() -> str:
    assert POSIX_INSTALLER.exists(), "T022 must add scripts/install.sh runtime guidance"
    return POSIX_INSTALLER.read_text(encoding="utf-8")


def test_posix_runtime_manager_never_requires_global_py_when_uv_is_missing(monkeypatch):
    monkeypatch.setattr("m32_bridge.installer.runtime_manager.which", lambda name: None)

    result = detect_uv_status(allow_user_install=False)

    assert result.global_py_required is False
    assert result.uv_status == "manual_action_required"
    assert result.manual_guidance
    assert "py" not in result.manual_guidance.lower()


def test_posix_runtime_manager_blocks_are_not_success():
    result = RuntimeManagerState(uv_status="blocked", manual_guidance="Network policy blocked user-local uv install.")

    assert result.ok is False
    assert result.global_py_required is False


def test_script_runtime_detects_uv_present_without_assume_env(monkeypatch, tmp_path):
    monkeypatch.delenv("M32_INSTALL_ASSUME_UV", raising=False)
    monkeypatch.delenv("M32_INSTALL_UV_BLOCKED", raising=False)
    monkeypatch.setattr(
        "m32_bridge.installer.script_runtime.detect_uv_status",
        lambda allow_user_install=False: RuntimeManagerState(uv_status="present"),
    )

    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
    )

    assert result["uv_detected"] is True
    assert result["uv_status"] == "present"
    assert result["installer_can_continue"] is True
    assert result["required_actions"] == []


def test_posix_script_defaults_to_user_local_no_admin_no_global_py():
    text = _install_sh_text().lower()

    assert "user-local" in text or "$home/.m32-bridge" in text
    assert "sudo" not in text
    assert "no administrator access is required" in text
    assert "no global py required" in text
    assert "python -m m32_bridge" not in text
    assert "uv" in text


def test_posix_missing_uv_dry_run_returns_structured_required_action(monkeypatch):
    monkeypatch.delenv("M32_INSTALL_ASSUME_UV", raising=False)
    monkeypatch.delenv("M32_INSTALL_UV_BLOCKED", raising=False)

    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        confirmed_dependency_actions=False,
        home=Path("/home/operator"),
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
    )

    assert result["ok"] is False
    assert result["status"] == "RUNTIME_SETUP_REQUIRED"
    assert result["error_code"] == "RUNTIME_SETUP_REQUIRED"
    assert result["uv_required"] is True
    assert result["uv_detected"] is False
    assert result["python_required"] is True
    assert result["global_python_required"] is False
    assert result["python_managed_by_uv"] is True
    assert result["installer_can_continue"] is False
    assert result["confirmation_required"] is True
    assert result["required_actions"][0]["action_id"] == "INSTALL_UV_USER_LOCAL"
    assert result["required_actions"][0]["requires_confirmation"] is True
    assert result["required_actions"][0]["risk_level"] == "user_local"
    assert result["required_actions"][0]["official_source_url"].startswith("https://")
    assert "sudo" not in result["required_actions"][0]["command_preview"].lower()


def test_posix_missing_uv_apply_without_confirmation_is_not_success(monkeypatch):
    monkeypatch.delenv("M32_INSTALL_ASSUME_UV", raising=False)

    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        confirmed_dependency_actions=False,
        home=Path("/home/operator"),
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
    )

    assert result["ok"] is False
    assert result["status"] == "UV_MISSING"
    assert result["error_code"] == "UV_MISSING_CONFIRMATION_REQUIRED"
    assert result["required_actions"]
    assert result["installer_can_continue"] is False
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
    assert result["osc_writes_sent"] == 0


def test_posix_github_raw_source_metadata_and_missing_uv_are_not_success(tmp_path):
    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        json_output=True,
        confirmed_dependency_actions=False,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
        install_source="github_raw",
        source_url="https://raw.githubusercontent.com/example/m32/main/scripts/install.sh",
        source_ref="main",
    )

    assert result["ok"] is False
    assert result["status"] == "RUNTIME_SETUP_REQUIRED"
    assert result["install_source"] == "github_raw"
    assert result["source_url"].startswith("https://raw.githubusercontent.com/")
    assert result["source_ref"] == "main"
    assert result["installer_can_continue"] is False
    assert result["required_actions"]
    assert result["admin_required"] is False
    assert result["global_python_required"] is False
    assert result["osc_writes_sent"] == 0


def test_posix_apply_offers_first_run_setup_without_running_it(tmp_path):
    uv_bin = tmp_path / "runtime" / "uv"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        confirmed_dependency_actions=True,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    applied = script_runtime.perform_apply_install("posix", result, uv_bin=str(uv_bin))

    assert applied["ok"] is True
    assert applied["first_run_setup"]["offered"] is True
    assert applied["first_run_setup"]["interactive"] is False
    assert applied["first_run_setup"]["attempted_path"] == "not_attempted"
    assert applied["first_run_setup"]["osc_writes_sent"] == 0
    assert applied["verification_guidance"]["offered"] is True
    assert "m32-bridge get-info" in applied["verification_guidance"]["commands"]
    assert applied["hardware_verified"] is False
    assert applied["production_live_ready"] is False
