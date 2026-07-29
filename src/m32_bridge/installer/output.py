from __future__ import annotations

from typing import Any, Literal


InstallerStatus = Literal[
    "fresh_install",
    "existing_install",
    "repair",
    "update",
    "already_current",
    "partial_failure",
    "failed",
    "UV_MISSING",
    "RUNTIME_SETUP_REQUIRED",
    "first_run_setup_required",
    "non_interactive_setup_required",
]

InstallerPlatform = Literal[
    "macos",
    "linux",
    "wsl",
    "windows_powershell",
    "windows_cmd",
    "raspberry_pi_os",
    "unsupported",
]

UvStatus = Literal["present", "installed_user_local", "blocked", "manual_action_required"]


def build_installer_output(
    *,
    status: InstallerStatus,
    platform: InstallerPlatform,
    app_path: str,
    launcher_path: str,
    uv_status: UvStatus,
    ok: bool = True,
    recommendations: list[str] | None = None,
    first_run_setup: dict[str, Any] | None = None,
    error_code: str | None = None,
    message: str | None = None,
    version: str | None = None,
    install_source: str | None = None,
    path_updated: bool | None = None,
    shell_profile: str | None = None,
    detected_shell: str | None = None,
    wsl_distribution: str | None = None,
    architecture: str | None = None,
    install_root: str | None = None,
    user_local: bool | None = None,
    admin_required: bool | None = None,
    uv_required: bool | None = None,
    uv_detected: bool | None = None,
    python_required: bool | None = None,
    global_python_required: bool | None = None,
    python_managed_by_uv: bool | None = None,
    installer_can_continue: bool | None = None,
    confirmation_required: bool | None = None,
    required_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "status": status,
        "platform": platform,
        "app_path": app_path,
        "launcher_path": launcher_path,
        "requires_admin": False,
        "global_py_required": False,
        "uv_status": uv_status,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "recommendations": recommendations or [],
    }
    optional = {
        "first_run_setup": first_run_setup,
        "error_code": error_code,
        "message": message,
        "version": version,
        "install_source": install_source,
        "path_updated": path_updated,
        "shell_profile": shell_profile,
        "detected_shell": detected_shell,
        "wsl_distribution": wsl_distribution,
        "architecture": architecture,
        "install_root": install_root,
        "user_local": user_local,
        "admin_required": admin_required,
        "uv_required": uv_required,
        "uv_detected": uv_detected,
        "python_required": python_required,
        "global_python_required": global_python_required,
        "python_managed_by_uv": python_managed_by_uv,
        "installer_can_continue": installer_can_continue,
        "confirmation_required": confirmation_required,
        "required_actions": required_actions,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    return payload
