from __future__ import annotations

from pathlib import Path

from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target
from m32_bridge.installer.script_runtime import _apply_user_local_install


ROOT = Path(__file__).resolve().parents[2]
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"


def _install_sh_text() -> str:
    assert POSIX_INSTALLER.exists(), "T022 must add scripts/install.sh before POSIX launcher tests can pass"
    return POSIX_INSTALLER.read_text(encoding="utf-8")


def test_posix_launcher_path_is_user_local_and_stable(tmp_path):
    target = installation_target(os_family="linux", shell_family="posix")
    location = default_install_location(target, home=tmp_path / "home" / "operator")

    assert location.launcher_path == tmp_path / "home" / "operator" / ".local" / "bin" / "m32-bridge"
    assert location.requires_admin is False


def test_posix_launcher_dispatches_health_without_global_py_requirement():
    text = _install_sh_text().lower()

    assert "~/.local/bin/m32-bridge" in text or "$home/.local/bin/m32-bridge" in text
    assert "m32-bridge health" in text
    assert "python -m m32_bridge" not in text
    assert "no global py required" in text
    assert "sudo" not in text


def test_posix_generated_launcher_is_not_recursive(tmp_path):
    app_path = tmp_path / "home" / "operator" / ".m32-bridge" / "app"
    launcher_path = tmp_path / "home" / "operator" / ".local" / "bin" / "m32-bridge"

    _apply_user_local_install(
        "posix",
        {
            "app_path": str(app_path),
            "launcher_path": str(launcher_path),
            "install_root": str(app_path.parent),
        },
    )

    text = launcher_path.read_text(encoding="utf-8")
    assert 'exec m32-bridge "$@"' not in text
    assert "m32_bridge.__main__" in text
    assert str(app_path) in text
    assert 'cd "$APP_DIR"' in text
    assert "--project" in text
