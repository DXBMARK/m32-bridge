"""Manual-copy MCP client guidance for X32-Bridge MCP."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from m32_bridge.config.runtime import default_user_config_path, resolve_runtime_config
from m32_bridge.installer.application_version import application_version, validate_project_version
from m32_bridge.installer.paths import default_install_location
from m32_bridge.installer.platforms import installation_target

PRODUCT = "X32-Bridge MCP"
PACKAGE = "m32-mcp-bridge"
SERVER_NAME = "x32-bridge-mcp"
ARGS = ["mcp-server"]
TRANSPORT = "stdio"
CLIENT_IDS = ("claude", "codex", "gemini", "antigravity", "chatgpt", "generic")


@dataclass(frozen=True)
class ClientProfile:
    id: str
    display_name: str
    local_stdio_supported: str
    remote_mcp_supported: str
    config_format: str
    config_location_hint: str
    restart_required: str
    verification_steps: tuple[str, ...]
    notes: tuple[str, ...]
    official_support_status: str
    generated_snippet: dict[str, Any] | None


def resolve_installed_launcher(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    local_app_data: Path | str | None = None,
    os_family: str | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    family = os_family or _os_family(env)
    target = installation_target(
        os_family=family,
        shell_family="cmd_launcher" if family == "windows" else "posix",
        architecture=None,
    )
    location = default_install_location(target, home=home, local_app_data=local_app_data or env.get("LOCALAPPDATA"))
    return {
        "app_path": str(location.app_path),
        "launcher_path": str(location.launcher_path),
        "launcher_exists": location.launcher_path.exists(),
        "launcher_executable": location.launcher_path.is_file() and _is_executable(location.launcher_path),
        "launcher_status": "installed" if location.launcher_path.exists() else "not installed",
        "required_action": None if location.launcher_path.exists() else "Complete the X32-Bridge MCP installation first.",
        "installation_state": "installed_launcher_present" if location.launcher_path.exists() else "launcher_missing",
    }


def render_mcp_guidance(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    os_family: str | None = None,
    client: str = "all",
    local_app_data: Path | str | None = None,
    version: str | None = None,
    read_runtime_config: bool = True,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    selected_client = client if client in {*CLIENT_IDS, "all"} else "all"
    launcher = resolve_installed_launcher(environ=env, home=home, local_app_data=local_app_data, os_family=os_family)
    resolved_version = (
        validate_project_version(version)
        if version is not None
        else application_version(launcher["app_path"], environ=env)
    )
    runtime_config_path = (home / ".m32-bridge" / "runtime.yaml") if home is not None else default_user_config_path()

    if read_runtime_config:
        resolution = resolve_runtime_config(
            environ=env,
            user_config_path=runtime_config_path,
            allow_project_local=False,
        )
        configured_host = resolution.effective_host
        configured_port = resolution.effective_port
        console_configured: bool | None = bool(
            resolution.effective_host
        )
        runtime_config_inspection = (
            "configured"
            if resolution.effective_host
            else "not_configured"
        )
    else:
        configured_host = None
        configured_port = None
        console_configured = None
        runtime_config_inspection = "not_checked"

    warnings = _environment_override_warnings(env)
    profiles = _profiles(launcher["launcher_path"])
    clients = {profile.id: _profile_payload(profile, launcher["launcher_path"]) for profile in profiles}
    visible_clients = clients if selected_client == "all" else {selected_client: clients[selected_client]}
    return {
        "ok": True,
        "status": "MCP_GUIDANCE_READY",
        "product": PRODUCT,
        "version": resolved_version,
        "server_name": SERVER_NAME,
        "launcher_path": launcher["launcher_path"],
        "launcher_exists": launcher["launcher_exists"],
        "launcher_executable": launcher["launcher_executable"],
        "launcher_status": launcher["launcher_status"],
        "required_action": launcher["required_action"],
        "installation_state": launcher["installation_state"],
        "transport": TRANSPORT,
        "command": launcher["launcher_path"],
        "args": list(ARGS),
        "runtime_config_path": str(runtime_config_path),
        "runtime_config_source": "~/.m32-bridge/runtime.yaml",
        "runtime_config_inspection": runtime_config_inspection,
        "console_configured": console_configured,
        "configured_host": configured_host,
        "configured_port": configured_port,
        "environment_required": {},
        "environment_overrides_present": warnings,
        "environment_variables": "none required",
        "automatic_client_config_write": False,
        "manual_copy_only": True,
        "manual_copy_wording": "Manual-copy only: paste the generated values into the MCP client yourself.",
        "embeds_host_port_by_default": False,
        "reads_saved_user_config_by_default": read_runtime_config,
        "config_written": False,
        "app_opened": False,
        "no_auto_config_write": True,
        "clients": visible_clients,
        "client_guidance": list(visible_clients.values()),
        "detected_clients": list(visible_clients.values()),
        "default_snippet": {"command": launcher["launcher_path"], "args": list(ARGS)},
        "advanced_override_examples": _advanced_override_examples(launcher["launcher_path"]),
        "opens_network_port": False,
        "raw_osc_available": False,
        "arbitrary_path_available": False,
        "shell_execution_available": False,
        "remote_mcp_available": False,
        "background_service_started": False,
        "osc_writes_sent": 0,
        "network_scan": False,
        "console_probe": "not_run",
        "hardware_verified": False,
        "production_live_ready": False,
    }


def render_mcp_guidance_text(payload: Mapping[str, Any], *, width: int = 80) -> str:
    launcher_status = "true" if payload.get("launcher_executable") else str(payload.get("launcher_status", "not installed"))
    lines = [
        "MCP CLIENT SETUP",
        "=" * 60,
        "",
        "INSTALLATION",
        "-" * 60,
        f"  Application            : {payload['product']}",
        f"  Version                : {payload['version']}",
        f"  Launcher               : {payload['launcher_path']}",
        f"  Launcher status        : {payload['launcher_status']}",
        f"  Launcher executable    : {launcher_status}",
        f"  Runtime config         : {payload['runtime_config_path']}",
        f"  Console configured     : {str(payload['console_configured']).lower()}",
        "",
        "CONFIGURATION PRINCIPLE",
        "-" * 60,
        "  One runtime config source: ~/.m32-bridge/runtime.yaml",
        "  Environment variables: none required for normal installed use.",
        "  Do not duplicate the console host or port in client environment variables.",
        "  Environment overrides take precedence over the saved runtime configuration.",
    ]
    for warning in payload.get("environment_overrides_present", []):
        lines.append(f"  Warning: {warning}")
    lines.extend(["", "CLIENT COMPATIBILITY", "-" * 60])
    clients = payload.get("clients", {})
    for key in CLIENT_IDS:
        if key not in clients:
            continue
        lines.extend(_client_text(clients[key]))
    lines.extend(
        [
            "",
            "SECURITY",
            "-" * 60,
            "  Manual-copy only.",
            "  Automatic client config write : no",
            "  Network scan                  : not used",
            "  Console probe                 : not run",
            "  OSC writes                    : 0",
            "  Host/port in client env       : not required",
            "",
            "VERIFICATION CHECKLIST",
            "-" * 60,
            "  1. Confirm the launcher path exists after installation.",
            "  2. Add the profile through the selected client's MCP settings surface.",
            "  3. Restart or refresh the MCP client.",
            "  4. Confirm x32-bridge-mcp is Ready, Running, or listed.",
            "  5. Run m32-bridge health if startup fails.",
            "",
            "End of MCP client setup",
        ]
    )
    return "\n".join(_wrap_lines(lines, width))


def _client_text(profile: Mapping[str, Any]) -> list[str]:
    name = str(profile["display_name"]).upper()
    lines = ["", name, "-" * 60]
    if profile["id"] == "chatgpt":
        lines.extend(
            [
                "  Direct local stdio connection : not available",
                "  Required transport            : remote MCP",
                "  Private/local deployment      : Secure MCP Tunnel or another",
                "                                  approved remote deployment method",
                "",
                "  The local command:",
                "    m32-bridge mcp-server",
                "  cannot be pasted directly into ChatGPT as a local command entry.",
                "  Current local installer readiness does not imply ChatGPT remote readiness.",
            ]
        )
        return lines
    lines.extend(
        [
            f"  Local stdio           : {profile['local_stdio_supported']}",
            f"  Generated config      : {profile['generated_config']}",
            "  Automatic write       : no",
            f"  Config location       : {profile['config_location_hint']}",
            f"  Restart required      : {profile['restart_required']}",
        ]
    )
    if profile["id"] == "claude":
        lines.extend(
            [
                "",
                *json.dumps(profile["generated_snippet"], indent=2).splitlines(),
                "",
                "  1. Open Claude Desktop.",
                "  2. Open Settings > Developer.",
                "  3. Select Edit Config.",
                "  4. Merge the x32-bridge-mcp entry into the existing mcpServers object.",
                "  5. Do not replace unrelated existing servers.",
                "  6. Save.",
                "  7. Restart Claude Desktop.",
                "  8. Confirm the server shows Running.",
                "  9. Use View Logs if startup fails.",
                "  Warning: Do not paste a second top-level mcpServers object.",
            ]
        )
    elif profile["id"] == "codex":
        lines.extend(
            [
                "  Server name : x32-bridge-mcp",
                f"  Command     : {profile['command']}",
                "  Arguments   : mcp-server",
                "  Environment : none required",
                "  Transport   : stdio",
                "  Add these values through the MCP configuration surface provided by your installed Codex version.",
            ]
        )
    elif profile["id"] == "gemini":
        lines.extend(
            [
                "",
                *json.dumps(profile["generated_snippet"], indent=2).splitlines(),
                "  User configuration    : ~/.gemini/settings.json",
                "  Project configuration : .gemini/settings.json",
                "  Run /mcp list and confirm x32-bridge-mcp is Ready.",
            ]
        )
    elif profile["id"] == "antigravity":
        lines.extend(
            [
                "  Server name : x32-bridge-mcp",
                "  Transport   : stdio",
                f"  Command     : {profile['command']}",
                "  Arguments   : mcp-server",
                "  Environment : none required",
                "  Use the MCP server settings surface available in the installed Antigravity version.",
                "  Field names and config locations may differ between releases.",
            ]
        )
    else:
        lines.extend(
            [
                "  Server name : x32-bridge-mcp",
                "  Transport   : stdio",
                f"  Command     : {profile['command']}",
                '  Arguments   : ["mcp-server"]',
                "  Environment : {}",
                "  Use this only in MCP clients that support local command-based stdio servers.",
            ]
        )
    return lines


def _profiles(launcher_path: str) -> tuple[ClientProfile, ...]:
    stdio_snippet = {"command": launcher_path, "args": list(ARGS)}
    return (
        ClientProfile(
            id="claude",
            display_name="Claude Desktop",
            local_stdio_supported="supported",
            remote_mcp_supported="not required for local desktop use",
            config_format="mcpServers JSON",
            config_location_hint="Claude Desktop Settings > Developer > Edit Config",
            restart_required="yes",
            verification_steps=("Confirm the server shows Running.", "Use View Logs if startup fails."),
            notes=("Merge the entry into the existing mcpServers object.", "Do not replace unrelated existing servers."),
            official_support_status="local stdio supported",
            generated_snippet={"mcpServers": {SERVER_NAME: stdio_snippet}},
        ),
        ClientProfile(
            id="codex",
            display_name="Codex",
            local_stdio_supported="supported when the installed Codex client accepts local MCP entries",
            remote_mcp_supported="client/version dependent",
            config_format="values for installed Codex MCP settings surface",
            config_location_hint="Use the MCP configuration surface provided by your installed Codex version.",
            restart_required="client/version dependent",
            verification_steps=("Confirm the server is listed by the installed Codex client.",),
            notes=("No canonical Codex config file path is defined by this project.",),
            official_support_status="values-only profile",
            generated_snippet=None,
        ),
        ClientProfile(
            id="gemini",
            display_name="Gemini CLI",
            local_stdio_supported="supported",
            remote_mcp_supported="not required for local CLI use",
            config_format="settings.json mcpServers entry",
            config_location_hint="~/.gemini/settings.json or .gemini/settings.json",
            restart_required="restart or refresh MCP servers if supported",
            verification_steps=("Run /mcp list.", "Confirm x32-bridge-mcp is Ready."),
            notes=("Use command/args for local stdio; do not use httpUrl for this profile.",),
            official_support_status="local stdio settings profile",
            generated_snippet={"mcpServers": {SERVER_NAME: stdio_snippet}},
        ),
        ClientProfile(
            id="antigravity",
            display_name="Antigravity",
            local_stdio_supported="client/version dependent",
            remote_mcp_supported="client/version dependent",
            config_format="generic MCP values",
            config_location_hint="version dependent; verify the installed MCP settings schema",
            restart_required="client/version dependent",
            verification_steps=("Verify the MCP settings schema in the installed version.",),
            notes=("Field names and config locations may differ between releases.",),
            official_support_status="generic local stdio profile",
            generated_snippet=None,
        ),
        ClientProfile(
            id="chatgpt",
            display_name="ChatGPT",
            local_stdio_supported="not supported",
            remote_mcp_supported="required",
            config_format="remote MCP endpoint, not local stdio JSON",
            config_location_hint="future remote MCP setup only",
            restart_required="not applicable",
            verification_steps=("Complete a separate remote MCP deployment design first.",),
            notes=("Secure MCP Tunnel or another approved remote deployment method is required for private/local servers.",),
            official_support_status="direct local stdio not available",
            generated_snippet=None,
        ),
        ClientProfile(
            id="generic",
            display_name="Generic MCP client",
            local_stdio_supported="supported when the client accepts command/args MCP entries",
            remote_mcp_supported="client dependent",
            config_format="command/args stdio values",
            config_location_hint="client-specific settings",
            restart_required="client dependent",
            verification_steps=("Confirm x32-bridge-mcp is Ready, Running, or listed.",),
            notes=("Use only with clients that support local command-based stdio servers.",),
            official_support_status="generic local stdio profile",
            generated_snippet={"server_name": SERVER_NAME, "transport": TRANSPORT, "command": launcher_path, "args": list(ARGS), "environment": {}},
        ),
    )


def _profile_payload(profile: ClientProfile, launcher_path: str) -> dict[str, Any]:
    command = _snippet_command(profile.generated_snippet) or (launcher_path if profile.id != "chatgpt" else "")
    return {
        "client_id": profile.id,
        "id": profile.id,
        "display_name": profile.display_name,
        "name": profile.display_name,
        "local_stdio_supported": profile.local_stdio_supported,
        "remote_mcp_supported": profile.remote_mcp_supported,
        "config_format": profile.config_format,
        "config_location_hint": profile.config_location_hint,
        "restart_required": profile.restart_required,
        "verification_steps": list(profile.verification_steps),
        "notes": list(profile.notes),
        "official_support_status": profile.official_support_status,
        "generated_snippet": profile.generated_snippet,
        "generated_config": "no" if profile.id == "chatgpt" else ("generic local stdio profile" if profile.id == "antigravity" else "yes"),
        "command": command,
        "args": list(ARGS) if profile.id != "chatgpt" else [],
        "transport": TRANSPORT if profile.id != "chatgpt" else "remote MCP required",
        "environment": {},
        "environment_required": {},
        "embeds_host_port": False,
        "config_written": False,
        "app_opened": False,
        "config_mode": "manual_copy",
        "status": "not_detected",
        "status_indicator": "inactive_grey",
        "next_steps": list(profile.verification_steps),
    }


def _snippet_command(snippet: Mapping[str, Any] | None) -> str:
    if not snippet:
        return ""
    if "command" in snippet:
        return str(snippet["command"])
    servers = snippet.get("mcpServers") if isinstance(snippet.get("mcpServers"), Mapping) else {}
    server = servers.get(SERVER_NAME) if isinstance(servers, Mapping) else {}
    return str(server.get("command", "")) if isinstance(server, Mapping) else ""


def _advanced_override_examples(launcher_path: str) -> list[dict[str, Any]]:
    return [
        {
            "label": "Advanced manual host override",
            "description": "Use only when you intentionally want the MCP server process to read a different console host from the environment.",
            "manual_only": True,
            "default": False,
            "config_mode": "manual_copy",
            "command": launcher_path,
            "args": list(ARGS),
            "env": {"M32_CONSOLE_HOST": "<console-host>"},
        },
        {
            "label": "Advanced manual port override",
            "description": "Use only when you intentionally want the MCP server process to read a non-default console port from the environment.",
            "manual_only": True,
            "default": False,
            "config_mode": "manual_copy",
            "command": launcher_path,
            "args": list(ARGS),
            "env": {"M32_CONSOLE_PORT": "10023"},
        },
    ]


def _environment_override_warnings(env: Mapping[str, str]) -> list[str]:
    warnings: list[str] = []
    if env.get("M32_CONSOLE_HOST"):
        warnings.append("M32_CONSOLE_HOST is set and overrides the saved runtime host.")
    if env.get("M32_CONSOLE_PORT"):
        warnings.append("M32_CONSOLE_PORT is set and overrides the saved runtime port.")
    if env.get("M32_CONFIG"):
        warnings.append("M32_CONFIG is set; custom config may override normal installed behaviour.")
    return warnings


def _wrap_lines(lines: list[str], width: int) -> list[str]:
    import textwrap

    wrapped: list[str] = []
    effective_width = max(min(width, 120), 40)
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        indent = len(line) - len(line.lstrip())
        wrapped.extend(textwrap.wrap(line, width=effective_width, subsequent_indent=" " * indent, break_long_words=False) or [""])
    return wrapped


def _os_family(env: Mapping[str, str]) -> str:
    if env.get("WSL_DISTRO_NAME"):
        return "wsl"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _is_executable(path: Path) -> bool:
    if not path.exists():
        return False
    if path.suffix.lower() in {".cmd", ".bat", ".exe"}:
        return True
    return bool(path.stat().st_mode & 0o111)
