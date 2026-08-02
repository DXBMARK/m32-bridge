"""User-local lifecycle guidance for installer surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target


def render_lifecycle_guidance(
    *,
    surface: str,
    home: Path | str | None = None,
    local_app_data: Path | str | None = None,
    app_path: Path | str | None = None,
    launcher_path: Path | str | None = None,
    config_path: Path | str | None = None,
    install_status: str = "already_current",
) -> dict[str, Any]:
    target = installation_target(
        os_family="windows" if surface == "windows" else "linux",
        shell_family="cmd_launcher" if surface == "windows" else "posix",
    )
    location = default_install_location(target, home=home, local_app_data=local_app_data)
    resolved_app_path = Path(app_path) if app_path is not None else location.app_path
    resolved_launcher_path = Path(launcher_path) if launcher_path is not None else location.launcher_path
    resolved_config_path = Path(config_path) if config_path is not None else _config_path(surface=surface, home=home, local_app_data=local_app_data)
    failure_state = install_status in {"partial_failure", "failed"}
    return {
        "ok": not failure_state,
        "status": "lifecycle_guidance",
        "result_status": install_status,
        "structured": True,
        "user_local": True,
        "requires_admin": False,
        "admin_required": False,
        "app_path": str(resolved_app_path),
        "launcher_path": str(resolved_launcher_path),
        "config_path": str(resolved_config_path),
        "actions": [
            _action("update", resolved_app_path, resolved_launcher_path, resolved_config_path),
            _action("repair", resolved_app_path, resolved_launcher_path, resolved_config_path),
            _action("uninstall", resolved_app_path, resolved_launcher_path, resolved_config_path),
        ],
        "path_guidance": {
            "path_visibility": location.path_visibility,
            "requires_new_terminal": True,
            "manual_path_action_may_be_required": True,
            "message": "Open a new terminal after PATH changes; if the launcher is still missing, add the user-local launcher directory manually.",
            "destructive_cleanup": False,
        },
        "partial_failure_recovery": _partial_failure_recovery(resolved_app_path, resolved_launcher_path, resolved_config_path),
        "release_guidance": {
            "github_public_repo_after_push": "https://github.com/DXBMARK/m32-bridge",
            "stable_install_command": "download-inspect-run scripts/install.sh or scripts/install.ps1",
            "version_tag_guidance": "Use a version/tag after the public repository has the installer changes pushed.",
            "release_manifest": "implemented",
            "sha256_checksums": "implemented",
            "raw_live_install_test": "deferred until after commit/push",
        },
        "future_packaging": _future_packaging(),
        "no_sudo": True,
        "no_system_paths": True,
        "destructive_cleanup": False,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _action(action: str, app_path: Path, launcher_path: Path, config_path: Path) -> dict[str, Any]:
    if action == "update":
        next_steps = [
            "Rerun the user-local installer from the inspected source.",
            "Preserve saved runtime config unless you intentionally change it later.",
            "Open a new terminal if PATH visibility changed.",
        ]
        result_status = "update"
        config_handling = "retain"
    elif action == "repair":
        next_steps = [
            "Rerun the user-local installer to restore missing app or launcher files.",
            "Do not delete saved runtime config during repair.",
            "Run m32-bridge health after repair.",
        ]
        result_status = "repair"
        config_handling = "retain"
    else:
        next_steps = [
            "Remove only the user-local app and launcher paths after reviewing them.",
            "Retain saved config and audit files by default.",
            "Remove saved config only after explicit confirmation.",
        ]
        result_status = "uninstall_guidance"
        config_handling = "ask"
    return {
        "action": action,
        "app_path": str(app_path),
        "launcher_path": str(launcher_path),
        "config_path": str(config_path),
        "config_handling": config_handling,
        "retains_config_by_default": True,
        "requires_explicit_config_removal_confirmation": action == "uninstall",
        "requires_admin": False,
        "user_local": True,
        "result_status": result_status,
        "next_steps": next_steps,
        "destructive_cleanup": False,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _partial_failure_recovery(app_path: Path, launcher_path: Path, config_path: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "claims_success": False,
        "recommended_action": "repair",
        "app_path": str(app_path),
        "launcher_path": str(launcher_path),
        "config_path": str(config_path),
        "manual_recovery_steps": [
            "Inspect the user-local app and launcher paths.",
            "Rerun the installer to repair missing files.",
            "Keep saved config and audit files unless you explicitly choose to remove them.",
        ],
        "destructive_cleanup": False,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _config_path(*, surface: str, home: Path | str | None, local_app_data: Path | str | None) -> Path:
    if surface == "windows":
        base = Path(local_app_data) if local_app_data is not None else Path.home() / "AppData" / "Local"
        return base / "M32Bridge" / "runtime.yaml"
    root = Path(home) if home is not None else Path.home()
    return root / ".m32-bridge" / "runtime.yaml"


def _future_packaging() -> list[dict[str, Any]]:
    kinds = [
        ".exe",
        ".msi",
        ".app",
        ".pkg",
        ".dmg",
        ".deb",
        ".rpm",
        "AppImage",
        "Raspberry Pi service/image",
        "Claude .mcpb",
        "Claude .dxt",
        "USB portable kit",
        "code signing",
    ]
    return [{"kind": kind, "status": "future_only", "implemented_now": False} for kind in kinds]
