from __future__ import annotations


def test_lifecycle_guidance_identifies_user_local_paths_and_actions(tmp_path):
    from m32_bridge.installer.lifecycle import render_lifecycle_guidance

    guidance = render_lifecycle_guidance(surface="posix", home=tmp_path)

    assert guidance["status"] == "lifecycle_guidance"
    assert guidance["user_local"] is True
    assert guidance["requires_admin"] is False
    assert guidance["app_path"] == str(tmp_path / ".m32-bridge" / "app")
    assert guidance["launcher_path"] == str(tmp_path / ".local" / "bin" / "m32-bridge")
    assert {action["action"] for action in guidance["actions"]} == {"update", "repair", "uninstall"}
    assert all(action["requires_admin"] is False for action in guidance["actions"])
    assert all(action["app_path"] == guidance["app_path"] for action in guidance["actions"])
    assert all(action["launcher_path"] == guidance["launcher_path"] for action in guidance["actions"])


def test_lifecycle_guidance_documents_config_retention_and_path_restart(tmp_path):
    from m32_bridge.installer.lifecycle import render_lifecycle_guidance

    guidance = render_lifecycle_guidance(surface="windows", local_app_data=tmp_path)

    uninstall = next(action for action in guidance["actions"] if action["action"] == "uninstall")
    assert uninstall["config_handling"] == "ask"
    assert uninstall["retains_config_by_default"] is True
    assert uninstall["requires_explicit_config_removal_confirmation"] is True
    assert "runtime.yaml" in uninstall["config_path"]
    assert guidance["path_guidance"]["requires_new_terminal"] is True
    assert "new terminal" in guidance["path_guidance"]["message"].lower()
    assert guidance["path_guidance"]["destructive_cleanup"] is False


def test_lifecycle_guidance_has_safety_constants(tmp_path):
    from m32_bridge.installer.lifecycle import render_lifecycle_guidance

    guidance = render_lifecycle_guidance(surface="posix", home=tmp_path)

    assert guidance["osc_writes_sent"] == 0
    assert guidance["hardware_verified"] is False
    assert guidance["production_live_ready"] is False
    assert guidance["no_sudo"] is True
    assert guidance["no_system_paths"] is True
    assert guidance["destructive_cleanup"] is False


def test_installer_scripts_advertise_lifecycle_guidance_without_admin_or_destructive_cleanup():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    combined = "\n".join(
        [
            (root / "scripts" / "install.sh").read_text(encoding="utf-8"),
            (root / "scripts" / "install.ps1").read_text(encoding="utf-8"),
        ]
    ).lower()

    assert "lifecycle guidance" in combined
    assert "update" in combined
    assert "repair" in combined
    assert "uninstall" in combined
    assert "retain saved config" in combined
    assert "sudo" not in combined
    assert "rm -rf" not in combined
