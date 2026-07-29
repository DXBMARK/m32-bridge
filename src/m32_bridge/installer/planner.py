from __future__ import annotations

from pathlib import Path
from typing import Any

from .output import build_installer_output
from .paths import default_install_location
from .platforms import InstallationTarget, installation_target
from .runtime_manager import RuntimeManagerState, detect_uv_status
from .state import determine_install_state


def plan_dry_run_install(
    *,
    target: InstallationTarget | None = None,
    platform: str = "macos",
    home: Path | str | None = None,
    local_app_data: Path | str | None = None,
    uv_state: RuntimeManagerState | None = None,
    current_version: str | None = None,
    target_version: str | None = None,
    app_exists: bool | None = None,
    launcher_exists: bool | None = None,
    partial_failure_marker: bool = False,
) -> dict[str, Any]:
    resolved_target = target or installation_target(os_family=_os_family(platform), shell_family=_shell_family(platform))
    location = default_install_location(resolved_target, home=home, local_app_data=local_app_data)
    runtime = uv_state or detect_uv_status()
    install_state = determine_install_state(
        location,
        app_exists=app_exists,
        launcher_exists=launcher_exists,
        current_version=current_version,
        target_version=target_version,
        partial_failure_marker=partial_failure_marker,
    )
    ok = install_state.status != "failed" and runtime.uv_status != "blocked"
    recommendations = [
        "Run m32-bridge health after install.",
        "Run m32-bridge setup for first-run console configuration.",
    ]
    if runtime.manual_guidance:
        recommendations.append(runtime.manual_guidance)

    return build_installer_output(
        ok=ok,
        status=install_state.status,
        platform=resolved_target.output_platform,
        app_path=str(location.app_path),
        launcher_path=str(location.launcher_path),
        uv_status=runtime.uv_status,
        recommendations=recommendations,
        version=target_version or current_version,
        install_source="local_checkout",
        path_updated=False,
        detected_shell=resolved_target.detected_shell,
        wsl_distribution=resolved_target.wsl_distribution,
        architecture=resolved_target.architecture,
        install_root=str(location.app_path.parent),
        user_local=True,
        admin_required=False,
        first_run_setup={
            "offered": False,
            "interactive": resolved_target.is_interactive,
            "attempted_path": "not_attempted",
            "classification": None,
            "osc_writes_sent": 0,
            "hardware_verified": False,
        },
    )


def _os_family(platform: str) -> Any:
    if platform == "windows_powershell" or platform == "windows_cmd":
        return "windows"
    return platform


def _shell_family(platform: str) -> Any:
    if platform == "windows_cmd":
        return "cmd_launcher"
    if platform == "windows_powershell":
        return "powershell"
    return "posix"
