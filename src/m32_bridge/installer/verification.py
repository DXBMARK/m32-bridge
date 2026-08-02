from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any, Mapping

from m32_bridge.config.runtime import resolve_runtime_config
from m32_bridge.installer.application_version import application_version
from m32_bridge.installer.ide_detector import detect_ide_clients
from m32_bridge.installer.mcp_guidance import render_mcp_guidance
from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target
from m32_bridge.installer.runtime_manager import (
    APPROVED_PYTHON_MINOR,
    PROJECT_PYTHON_RANGE,
    detect_uv_status,
    inspect_runtime,
    managed_python_policy,
)



NEXT_COMMANDS = [
    "m32-bridge health",
    "m32-bridge setup",
    "m32-bridge get-info",
    "m32-bridge detect-device",
    "m32-bridge doctor-runtime",
]


def render_post_install_verification(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    local_app_data: Path | str | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    env = dict(environ or {})
    target = _target_from_environment(env)
    location = default_install_location(target, home=home, local_app_data=local_app_data or env.get("LOCALAPPDATA"))
    resolved_version = application_version(location.app_path, environ=env)
    runtime = detect_uv_status()
    runtime_info = inspect_runtime(environ=env)
    uv_detected = runtime.uv_status in {"present", "installed_user_local"}
    resolved_config_path = config_path or _default_config_path(home=home)
    resolution = resolve_runtime_config(environ=env, user_config_path=resolved_config_path, allow_project_local=False)
    surface = "windows" if target.os_family == "windows" else "posix"
    required_actions = [] if uv_detected else [_uv_required_action(surface, _dependency_target_root(surface, home, local_app_data))]

    mcp_guidance = render_mcp_guidance(
        environ=env,
        home=home,
        os_family=target.os_family,
        local_app_data=local_app_data,
        version=resolved_version,
    )

    return {
        "ok": True,
        "status": "verification_guidance",
        "structured": True,
        "version": resolved_version,
        "install_source": "local_checkout",
        "platform": target.output_platform,
        "os_family": target.os_family,
        "wsl_distribution": target.wsl_distribution,
        "architecture": target.architecture,
        "install_path": str(location.app_path),
        "app_path": str(location.app_path),
        "launcher_path": str(location.launcher_path),
        "path_updated": False,
        "shell_profile": _shell_profile(target.detected_shell),
        "detected_shell": target.detected_shell or "unknown",
        "uv_required": True,
        "uv_detected": uv_detected,
        "uv_status": runtime.uv_status,
        "python_required": True,
        "global_py_required": False,
        "global_python_required": False,
        "python_managed_by_uv": True,
        "managed_python_policy": managed_python_policy(),
        "approved_python_minor": APPROVED_PYTHON_MINOR,
        "project_python_range": PROJECT_PYTHON_RANGE,
        "runtime_info": runtime_info,
        "config_path": str(resolved_config_path),
        "config_present": resolved_config_path.exists(),
        "configured_host": resolution.effective_host,
        "configured_port": resolution.effective_port,
        "detected_clients": detect_ide_clients(environ=env, home=home, os_family=target.os_family),
        "mcp_guidance": mcp_guidance,
        "next_commands": list(NEXT_COMMANDS),
        "verification_commands": [_verification_command(command) for command in NEXT_COMMANDS],
        "launcher_health": launcher_verification_metadata(surface=surface, home=home, local_app_data=local_app_data),
        "console_probe_attempted": False,
        "attempted_path": None,
        "scan_attempted": False,
        "guessed_host": None,
        "error_code": resolution.error_code,
        "message": "Post-install verification guidance is available without console contact.",
        "required_actions": required_actions,
        "recommendations": [
            "Run m32-bridge health first; it does not require console connectivity.",
            "Run m32-bridge setup before /info-based commands if no console host is configured.",
            "Manual-copy MCP guidance uses m32-bridge mcp-server as a local stdio command and writes no client config.",
        ],
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def launcher_verification_metadata(
    *,
    surface: str,
    home: Path | None = None,
    local_app_data: Path | str | None = None,
) -> dict[str, Any]:
    target = installation_target(os_family="windows" if surface == "windows" else "linux", shell_family="cmd_launcher" if surface == "windows" else "posix")
    location = default_install_location(target, home=home, local_app_data=local_app_data)
    return {
        "command": "m32-bridge health",
        "launcher_path": str(location.launcher_path),
        "requires_console_config": False,
        "uses_global_py": False,
        "expected_write_count": 0,
        "success_output": "health reports CLI/runtime status without console connectivity.",
        "failure_output": "launcher missing or runtime setup required; run install-status for paths.",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _target_from_environment(env: Mapping[str, str]) -> Any:
    os_family = _os_family(env)
    return installation_target(
        os_family=os_family,
        architecture=platform.machine() or None,
        detected_shell=_detected_shell(env),
        wsl_distribution=env.get("WSL_DISTRO_NAME"),
    )


def _verification_command(command: str) -> dict[str, Any]:
    requires_config = command not in {"m32-bridge health", "m32-bridge setup"}
    attempted_path = "/info" if command in {"m32-bridge setup", "m32-bridge get-info", "m32-bridge detect-device"} else None
    return {
        "command": command,
        "requires_console_config": requires_config,
        "attempted_path": attempted_path,
        "expected_write_count": 0,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _default_config_path(*, home: Path | None) -> Path:
    if home is not None:
        return home / ".m32-bridge" / "runtime.yaml"
    return Path.home() / ".m32-bridge" / "runtime.yaml"


def _dependency_target_root(surface: str, home: Path | None, local_app_data: Path | str | None) -> Path:
    if surface == "windows":
        return Path(local_app_data) if local_app_data is not None else Path.home() / "AppData" / "Local"
    return home or Path.home()


def _uv_required_action(surface: str, target_root: Path) -> dict[str, Any]:
    if surface == "windows":
        command_preview = "Invoke-RestMethod downloads the official uv installer to a temporary file; exact INSTALL confirmation required; then uv python install 3.13"
        target_paths = [str(target_root / "M32Bridge" / "runtime" / "uv")]
    else:
        command_preview = "curl downloads the official uv installer to a temporary file (wget/manual fallback); exact INSTALL confirmation required; then uv python install 3.13"
        target_paths = [str(target_root / ".local" / "bin" / "uv")]
    return {
        "action_id": "INSTALL_UV_USER_LOCAL",
        "title": "Install uv in user space",
        "reason": "M32 Bridge uses uv-managed CPython 3.13 without modifying system Python or default aliases.",
        "command_preview": command_preview,
        "requires_confirmation": True,
        "risk_level": "user_local",
        "target_paths": target_paths,
        "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
        "user_can_skip": False,
    }


def _detected_shell(env: Mapping[str, str]) -> str:
    shell = Path(env.get("SHELL", "")).name
    if shell in {"zsh", "bash", "fish"}:
        return shell
    if shell in {"pwsh", "powershell"}:
        return "powershell"
    if sys.platform.startswith("win"):
        return "powershell"
    return "unknown"


def _shell_profile(shell: str | None) -> str | None:
    return {
        "zsh": "~/.zshrc",
        "bash": "~/.bashrc",
        "fish": "~/.config/fish/config.fish",
        "powershell": "PowerShell user profile",
        "cmd": "User PATH",
    }.get(shell or "unknown")


def _os_family(env: Mapping[str, str]) -> str:
    if env.get("WSL_DISTRO_NAME"):
        return "wsl"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
