from __future__ import annotations

import platform
import socket
import sys
from pathlib import Path
from typing import Any, Callable

from m32_bridge.cli import setup_runtime
from m32_bridge.config.runtime import default_user_config_path
from m32_bridge.installer.ide_detector import detect_ide_clients
from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target
from m32_bridge.installer.runtime_manager import RuntimeManagerState, detect_uv_status
from m32_bridge.installer.script_runtime import _uv_required_action
from m32_bridge.installer.tty_app import handle_tty_command, installer_contact_text, installer_help_text

BANNER = "DXBMARK M32 BRIDGE"
ConnectivityChecker = Callable[[str, int, float], bool]


def environment_summary(
    *,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
    internet_checker: ConnectivityChecker | None = None,
    github_checker: ConnectivityChecker | None = None,
) -> dict[str, Any]:
    env = environ or {}
    os_name = _os_family(env)
    target = installation_target(
        os_family=os_name,
        architecture=platform.machine() or None,
        detected_shell=_detected_shell(env),
        wsl_distribution=env.get("WSL_DISTRO_NAME"),
    )
    location = default_install_location(target, home=home, local_app_data=env.get("LOCALAPPDATA"))
    uv_state = detect_uv_status()
    uv_detected = uv_state.uv_status in {"present", "installed_user_local"}
    return {
        "os": target.output_platform,
        "architecture": target.architecture,
        "detected_shell": target.detected_shell or "unknown",
        "wsl_distribution": target.wsl_distribution,
        "recommended_mode": "interactive_first_run" if uv_detected else "runtime_setup_required",
        "surface": "windows" if target.os_family == "windows" else "posix",
        "internet_status": check_internet_connectivity(checker=internet_checker),
        "github_install_source": "configured: github source archive",
        "github_reachability": "not_checked",
        "uv_detected": uv_detected,
        "uv_status": uv_state.uv_status,
        "python_managed_by_uv": True,
        "app_path": str(location.app_path),
        "launcher_path": str(location.launcher_path),
        "path_status": location.path_visibility,
    }


def non_tty_setup_response(
    *,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
    internet_checker: ConnectivityChecker | None = None,
    github_checker: ConnectivityChecker | None = None,
) -> dict[str, Any]:
    summary = environment_summary(environ=environ, home=home, internet_checker=internet_checker, github_checker=github_checker)
    target_root = _dependency_target_root(summary["surface"], environ=environ, home=home)
    required_actions = [] if summary["uv_detected"] else [_first_run_uv_required_action(summary["surface"], target_root)]
    return {
        "ok": False,
        "status": "RUNTIME_SETUP_REQUIRED" if required_actions else "NO_CONSOLE_HOST",
        "error_code": "NO_CONSOLE_HOST",
        "message": "Non-TTY setup does not prompt. Provide --host or run in a terminal.",
        "configured_host": None,
        "configured_port": None,
        "attempted_path": "/info",
        "latency_ms": None,
        "exception_type": None,
        "structured": True,
        "environment": summary,
        "required_actions": required_actions,
        "clients": detect_ide_clients(environ=environ, home=home, os_family=_client_os_family(summary)),
        "next_commands": _next_commands(),
        "recommendations": ["Run m32-bridge setup in an interactive terminal.", "Run m32-bridge setup --host <console-ip> --json for automation."],
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "guessed_host": None,
        "scan_attempted": False,
    }


def render_tty_intro(summary: dict[str, Any], clients: list[dict[str, Any]]) -> str:
    client_lines = [f"{_dot(c)} {c['name']}: {c['status']}" for c in clients]
    setup_panel = "\n".join(
        [
            BANNER,
            "DXBMARK LLC | dxbmark.com",
            "Type / for interactive menu | Type /help for list",
            "",
            "[System]",
            f"OS: {summary['os']}",
            f"Architecture: {summary['architecture']}",
            f"Shell: {summary['detected_shell']}",
            f"WSL: {summary['wsl_distribution'] or 'not_detected'}",
            "",
            "[Runtime]",
            f"Recommended mode: {summary['recommended_mode']}",
            f"uv: {'green dot detected' if summary['uv_detected'] else 'grey dot missing'}",
            f"Python: managed by uv",
            f"Internet: {summary['internet_status']}",
            f"Source configuration: {summary['github_install_source']}",
            f"Reachability: {summary['github_reachability']}",
            "",
            "[Clients]",
            *client_lines,
            "",
            "[Console Setup]",
            "Console IP: required; no guessing or scan",
            "Port: default 10023",
            "",
            "[Help]",
            "/help  /contact  /status  /clear  /exit",
            "Status: green dot detected / grey dot not detected",
        ]
    )
    return setup_panel


def help_text() -> str:
    return installer_help_text(width=80)


def contact_text() -> str:
    return installer_contact_text(width=80)


def run_setup_probe(
    *,
    host: str | None,
    port: int | None = None,
    target_type: str = "unknown",
    label: str | None = None,
    environment: str | None = None,
    confirm_save: bool = False,
    config_path: Path | None = None,
    config_scope: str = "user",
    timeout: float = 0.5,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
    probe_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if host is None:
        payload = non_tty_setup_response(environ=environ, home=home)
        payload["status"] = "SETUP_INPUT_REQUIRED"
        payload["message"] = "Console host is required. No IP guessing or scan was attempted."
        return payload
    summary = environment_summary(environ=environ, home=home)
    result = setup_runtime(
        host=host,
        port=port or 10023,
        target_type=target_type,
        label=label,
        environment=environment,
        save=True,
        confirm_save=confirm_save,
        config_path=config_path,
        config_scope=config_scope,
        timeout=timeout,
        probe_result=probe_result,
    )
    result["config_path"] = result.get("config_path") or str(config_path or default_user_config_path())
    result["next_commands"] = _next_commands()
    result["detected_clients"] = detect_ide_clients(environ=environ, home=home, os_family=_client_os_family(summary))
    result["install_path"] = summary["app_path"]
    result["launcher_path"] = summary["launcher_path"]
    result["environment_summary"] = summary
    result["guessed_host"] = None
    result["scan_attempted"] = False
    result["osc_writes_sent"] = 0
    result["hardware_verified"] = False
    result["production_live_ready"] = False
    return result


def interactive_wizard(
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    summary = environment_summary(environ=environ)
    clients = detect_ide_clients(environ=environ, os_family=_client_os_family(summary))
    output_func(render_tty_intro(summary, clients))
    host = input_func("Console IP: ").strip()
    if host in {"/help", "help", "/contact", "contact", "/status", "status", "/clear", "clear"}:
        command_result = {
            "ok": False,
            "status": "SETUP_INPUT_REQUIRED",
            "platform": summary["os"],
            "uv_status": summary["uv_status"],
            "uv_detected": summary["uv_detected"],
            "install_source": summary["github_install_source"],
            "source_url": "not_configured",
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }
        command = f"/{host}" if not host.startswith("/") else host
        output, should_stop = handle_tty_command(command, command_result, color=False)
        output_func(output or help_text())
        if should_stop:
            return {"ok": False, "status": "SETUP_CANCELLED", "osc_writes_sent": 0, "hardware_verified": False, "production_live_ready": False}
        host = input_func("Console IP: ").strip()
    if host in {"/exit", "exit", "quit", "q"}:
        return {"ok": False, "status": "SETUP_CANCELLED", "osc_writes_sent": 0, "hardware_verified": False, "production_live_ready": False}
    if host in {"/contact", "contact"}:
        output_func(contact_text())
        host = input_func("Console IP: ").strip()
    port_text = input_func("Port [10023]: ").strip()
    label = input_func("Label/environment: ").strip() or None
    target_type = input_func("Target type [unknown]: ").strip() or "unknown"
    save_answer = input_func("Save config? type yes to confirm: ").strip().lower()
    return run_setup_probe(
        host=host,
        port=int(port_text) if port_text else 10023,
        target_type=target_type,
        label=label,
        confirm_save=save_answer == "yes",
        environ=environ,
    )


def _dot(client: dict[str, Any]) -> str:
    return "green dot" if client["status"] == "detected" else "grey dot"


def _next_commands() -> list[str]:
    return [
        "m32-bridge health",
        "m32-bridge setup",
        "m32-bridge get-info",
        "m32-bridge detect-device",
        "m32-bridge doctor-runtime",
        "m32-bridge mcp-server",
    ]


def _detected_shell(env: dict[str, str]) -> str:
    shell = Path(env.get("SHELL", "")).name
    if shell in {"zsh", "bash", "fish"}:
        return shell
    if env.get("PSModulePath"):
        return "powershell"
    return "unknown"


def _os_family(env: dict[str, str]) -> str:
    if env.get("WSL_DISTRO_NAME"):
        return "wsl"
    if env.get("LOCALAPPDATA") or env.get("PSModulePath"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def check_internet_connectivity(*, checker: ConnectivityChecker | None = None, timeout: float = 0.25) -> str:
    return _check_connectivity("1.1.1.1", 443, timeout=timeout, checker=checker)


def check_github_install_source(*, checker: ConnectivityChecker | None = None, timeout: float = 0.25) -> str:
    return _check_connectivity("raw.githubusercontent.com", 443, timeout=timeout, checker=checker)


def _check_connectivity(
    host: str,
    port: int,
    *,
    timeout: float,
    checker: ConnectivityChecker | None,
) -> str:
    try:
        if checker is not None:
            return "ONLINE" if checker(host, port, timeout) else "OFFLINE"
        with socket.create_connection((host, port), timeout=timeout):
            return "ONLINE"
    except TimeoutError:
        return "TIMEOUT"
    except socket.timeout:
        return "TIMEOUT"
    except PermissionError:
        return "UNKNOWN"
    except OSError:
        return "UNAVAILABLE"


def _dependency_target_root(surface: str, *, environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    env = environ or {}
    if surface == "windows":
        return Path(env.get("LOCALAPPDATA") or home or (Path.home() / "AppData" / "Local"))
    return home or Path(env.get("HOME") or Path.home())


def _first_run_uv_required_action(surface: str, target_root: Path) -> dict[str, Any]:
    action = dict(_uv_required_action(surface, target_root))
    if surface == "windows":
        action["download_guidance"] = "Use PowerShell irm / Invoke-RestMethod guidance after explicit confirmation."
    else:
        action["download_guidance"] = "Use curl when available, wget fallback, or manual download after explicit confirmation."
        action["fallbacks"] = ["curl", "wget", "manual_download"]
    return action


def _client_os_family(summary: dict[str, Any]) -> str:
    platform_name = str(summary["os"])
    if platform_name.startswith("windows"):
        return "windows"
    return platform_name
