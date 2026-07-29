from __future__ import annotations

from pathlib import Path

from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target
from m32_bridge.installer.script_runtime import _apply_user_local_install


ROOT = Path(__file__).resolve().parents[2]
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"


def _install_ps1_text() -> str:
    assert WINDOWS_INSTALLER.exists(), "T024 must add scripts/install.ps1 before Windows launcher tests can pass"
    return WINDOWS_INSTALLER.read_text(encoding="utf-8")


def test_windows_cmd_launcher_path_is_user_local(tmp_path):
    target = installation_target(os_family="windows", shell_family="cmd_launcher")
    local_app_data = tmp_path / "LocalAppData"
    location = default_install_location(target, local_app_data=local_app_data)

    assert location.launcher_path == local_app_data / "M32Bridge" / "bin" / "m32-bridge.cmd"
    assert location.requires_admin is False


def test_windows_installer_plans_cmd_compatible_launcher_without_global_py():
    text = _install_ps1_text().lower()

    assert "m32-bridge.cmd" in text
    assert "%localappdata%\\m32bridge\\bin\\m32-bridge.cmd" in text or "$env:localappdata" in text
    assert "m32-bridge health" in text
    assert "cmd" in text
    assert " py " not in f" {text} "
    assert "global py" not in text


def test_windows_generated_launcher_is_not_recursive(tmp_path):
    app_path = tmp_path / "LocalAppData" / "M32Bridge" / "app"
    launcher_path = tmp_path / "LocalAppData" / "M32Bridge" / "bin" / "m32-bridge.cmd"

    _apply_user_local_install(
        "windows",
        {
            "app_path": str(app_path),
            "launcher_path": str(launcher_path),
            "install_root": str(app_path.parent),
        },
    )

    text = launcher_path.read_text(encoding="utf-8")
    assert "m32-bridge %*" not in text.lower()
    assert "m32_bridge.__main__" in text
    assert str(app_path) in text
    assert "/d \"%M32_BRIDGE_APP_DIR%\"" in text
    assert "--project" in text
