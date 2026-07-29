from __future__ import annotations

import pytest

from m32_bridge.installer.planner import plan_dry_run_install


@pytest.mark.parametrize(
    ("platform", "surface_hint"),
    [
        ("macos", "posix"),
        ("linux", "posix"),
        ("wsl", "posix"),
        ("raspberry_pi_os", "posix"),
        ("windows_powershell", "windows"),
        ("windows_cmd", "windows"),
    ],
)
def test_final_cross_platform_installer_gate_is_user_local_and_safe(tmp_path, platform, surface_hint):
    local_app_data = tmp_path / "LocalAppData"
    home = tmp_path / "home"

    result = plan_dry_run_install(platform=platform, home=home, local_app_data=local_app_data)

    assert result["platform"] == platform
    assert result["requires_admin"] is False
    assert result["global_py_required"] is False
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
    if surface_hint == "windows":
        assert str(local_app_data) in result["app_path"]
        assert result["launcher_path"].endswith("m32-bridge.cmd")
    else:
        assert str(home) in result["app_path"]
        assert result["launcher_path"].endswith("m32-bridge")


def test_final_cross_platform_scripts_keep_expected_bootstrap_surfaces():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    install_sh = (root / "scripts" / "install.sh").read_text(encoding="utf-8").lower()
    install_ps1 = (root / "scripts" / "install.ps1").read_text(encoding="utf-8").lower()

    assert "curl" in install_sh
    assert "wget" in install_sh
    assert "manual download" in install_sh
    assert "irm" in install_ps1 or "invoke-restmethod" in install_ps1
    assert "global_py_required=false" in install_sh
    assert "global_python_required=false" in install_ps1
    assert "admin_required=false" in install_sh
    assert "admin_required=false" in install_ps1
    assert "/set" not in install_sh
    assert "/set" not in install_ps1
