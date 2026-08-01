from __future__ import annotations

from pathlib import Path

from m32_bridge.installer import script_runtime
from m32_bridge.installer.runtime_manager import RuntimeManagerState, detect_uv_status


ROOT = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"


def _install_ps1_text() -> str:
    assert WINDOWS_INSTALLER.exists(), "T024 must add scripts/install.ps1 runtime and execution-policy guidance"
    return WINDOWS_INSTALLER.read_text(encoding="utf-8")


def test_windows_runtime_manager_never_requires_python_or_py_when_uv_is_missing(monkeypatch):
    monkeypatch.setattr("m32_bridge.installer.runtime_manager.which", lambda name: None)

    result = detect_uv_status(allow_user_install=False)

    assert result.global_py_required is False
    assert result.uv_status == "manual_action_required"
    assert result.manual_guidance
    assert "python" not in result.manual_guidance.lower()
    assert " py " not in f" {result.manual_guidance.lower()} "


def test_windows_runtime_manager_blocked_state_requires_manual_action_not_success():
    result = RuntimeManagerState(uv_status="blocked", manual_guidance="PowerShell policy blocked user-local uv install.")

    assert result.ok is False
    assert result.global_py_required is False


def test_windows_script_guides_execution_policy_user_local_runtime_and_no_global_py():
    text = _install_ps1_text().lower()

    assert "executionpolicy" in text or "execution policy" in text
    assert "$env:localappdata" in text or "%localappdata%" in text
    assert "uv" in text
    assert "no administrator access is required" in text
    assert "start-process -verb runas" not in text
    assert "no global py required" in text
    assert "python -m m32_bridge" not in text


def test_windows_missing_uv_json_result_is_structured_and_non_interactive(monkeypatch, tmp_path):
    monkeypatch.delenv("M32_INSTALL_ASSUME_UV", raising=False)

    result = script_runtime.build_install_result(
        surface="windows",
        platform="windows_powershell",
        dry_run=True,
        json_output=True,
        confirmed_dependency_actions=False,
        local_app_data=tmp_path / "LocalAppData",
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
    )

    assert result["ok"] is False
    assert result["status"] == "RUNTIME_SETUP_REQUIRED"
    assert result["error_code"] == "RUNTIME_SETUP_REQUIRED"
    assert result["required_actions"]
    action = result["required_actions"][0]
    assert action["action_id"] == "INSTALL_UV_USER_LOCAL"
    assert action["requires_confirmation"] is True
    assert action["official_source_url"].startswith("https://")
    assert "irm" in action["command_preview"].lower()
    assert result["installer_can_continue"] is False
    assert result["confirmation_required"] is True


def test_windows_missing_uv_apply_without_confirmation_is_not_success(tmp_path):
    result = script_runtime.build_install_result(
        surface="windows",
        platform="windows_powershell",
        dry_run=False,
        confirmed_dependency_actions=False,
        local_app_data=tmp_path / "LocalAppData",
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
    )

    assert result["ok"] is False
    assert result["status"] == "UV_MISSING"
    assert result["required_actions"][0]["user_can_skip"] is False
    assert result["global_python_required"] is False


def test_windows_apply_offers_first_run_setup_without_running_it(tmp_path):
    uv_bin = tmp_path / "Runtime Tools" / "uv.exe"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_bytes(b"fake uv")
    result = script_runtime.build_install_result(
        surface="windows",
        platform="windows_powershell",
        dry_run=False,
        confirmed_dependency_actions=True,
        local_app_data=tmp_path / "LocalAppData",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    applied = script_runtime.perform_apply_install("windows", result, uv_bin=str(uv_bin))

    assert applied["ok"] is True
    assert applied["first_run_setup"]["offered"] is True
    assert applied["first_run_setup"]["interactive"] is False
    assert applied["first_run_setup"]["attempted_path"] == "not_attempted"
    assert applied["first_run_setup"]["osc_writes_sent"] == 0
    assert applied["verification_guidance"]["offered"] is True
    assert "m32-bridge doctor-runtime" in applied["verification_guidance"]["commands"]
    assert applied["hardware_verified"] is False
    assert applied["production_live_ready"] is False
