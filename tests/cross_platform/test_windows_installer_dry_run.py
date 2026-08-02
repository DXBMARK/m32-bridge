from __future__ import annotations

from pathlib import Path

from m32_bridge.installer.planner import plan_dry_run_install


ROOT = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"


def _install_ps1_text() -> str:
    assert WINDOWS_INSTALLER.exists(), "T024 must add scripts/install.ps1 for the Windows installer surface"
    return WINDOWS_INSTALLER.read_text(encoding="utf-8")


def test_windows_powershell_dry_run_is_user_local_and_status_only(tmp_path):
    local_app_data = tmp_path / "LocalAppData"

    result = plan_dry_run_install(platform="windows_powershell", local_app_data=local_app_data)

    assert result["platform"] == "windows_powershell"
    assert result["app_path"] == str(local_app_data / "M32Bridge" / "app")
    assert result["launcher_path"] == str(local_app_data / "M32Bridge" / "bin" / "m32-bridge.cmd")
    assert result["requires_admin"] is False
    assert result["global_py_required"] is False
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_windows_installer_uses_powershell_irm_and_only_curl_exe_as_optional_fallback():
    text = _install_ps1_text().lower()

    assert "install.ps1" in text
    assert "irm" in text or "invoke-restmethod" in text
    assert "powershell invoke-webrequest/invoke-restmethod available" in text
    assert "does not install wget or curl" in text
    assert "+971505121583" in text
    assert "download" in text
    assert "inspect" in text
    assert "dry-run" in text or "dry_run" in text
    assert "no /set" in text
    assert "send_raw_osc" not in text
    assert "state-changing osc" not in text


def test_windows_script_supports_local_checkout_and_github_bootstrap_metadata():
    text = _install_ps1_text()

    assert "src\\m32_bridge" in text or "src/m32_bridge" in text
    assert "pyproject.toml" in text
    assert "local_checkout" in text
    assert "github_release_asset" in text
    assert "github_commit_archive" in text
    assert "github_main" in text
    assert "M32_INSTALL_SOURCE_URL" in text
    assert "M32_INSTALL_SOURCE_REF" in text
    assert "secure_bootstrap.py" in text
    assert "bootstrap-plan.json" in text
    assert "--bootstrap-plan" in text
    assert "Expand-Archive" not in text
    assert "Resolve-GithubValue" not in text
    assert "m32-ai-mcp-bridge" not in text
    assert "source_url" in text
    assert "installer_can_continue" in text
    assert "required_actions" in text


def test_windows_missing_uv_payload_is_not_fresh_install_success():
    text = _install_ps1_text().lower()
    missing_uv_block = text.split("if ($null -ne $uvcommand)", 1)[1].split("} else {", 1)[1]

    assert 'status = "runtime_setup_required"' in text
    assert "installer_can_continue = $false" in text
    assert "required_actions" in text
    assert 'ok = $false' in text
    assert 'status: fresh_install' not in missing_uv_block
    assert "app_path: $apppath" not in missing_uv_block
    assert "launcher_path: $launcherpath" not in missing_uv_block
    assert "app_path: $($payload.app_path)" in missing_uv_block
    assert "launcher_path: $($payload.launcher_path)" in missing_uv_block
    assert "start-process -verb runas" not in text


def test_windows_installer_wizard_mentions_dxbmark_style_with_plain_json_fallback():
    text = _install_ps1_text().lower()

    assert "dxbmark" in text
    assert "tty" in text
    assert '$runtimeargs += "--tty"' in text
    assert "48;2;36;57;71" in text
    assert "write-canvasline" in text
    assert "windowwidth" in text
    assert "non-tty" in text or "non_tty" in text
    assert "system check" in text
    assert "source check" in text
    assert "install plan" in text
    assert "required actions" in text
    assert "json" in text
    assert "raw interactive theme" not in text
