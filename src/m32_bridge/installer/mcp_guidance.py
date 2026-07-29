"""Manual-copy MCP guidance for installer and post-install surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from m32_bridge.installer.ide_detector import detect_ide_clients


COMMAND = "m32-bridge"
ARGS = ["mcp-server"]


CLIENT_NEXT_STEPS = {
    "claude_desktop": [
        "Open Claude Desktop settings yourself.",
        "Add a local stdio MCP server entry and paste the snippet.",
        "Restart Claude Desktop only after saving the manual change.",
    ],
    "codex": [
        "Add a local stdio MCP server entry in your Codex MCP settings.",
        "Paste the snippet without host or port values.",
        "Run m32-bridge health first if the launcher is not found.",
    ],
    "gemini": [
        "Open Gemini MCP settings yourself if your build supports local MCP.",
        "Paste the local stdio snippet manually.",
        "Keep console host and port in the saved m32-bridge config unless you intentionally use advanced overrides.",
    ],
    "antigravity": [
        "Open Antigravity MCP settings yourself.",
        "Create a local stdio server entry and paste the snippet.",
        "Keep this as a local stdio server entry.",
    ],
    "chatgpt_desktop": [
        "Use local connector or MCP settings yourself if available.",
        "Paste the local stdio snippet manually.",
        "Keep this as a local stdio server entry.",
    ],
    "vscode": [
        "Open VS Code MCP settings yourself.",
        "Add a local stdio server entry and paste the snippet.",
        "Use the same snippet for compatible VS Code profiles.",
    ],
    "cursor": [
        "Open Cursor MCP settings yourself.",
        "Add a local stdio server entry and paste the snippet.",
        "Keep host and port out of the default snippet.",
    ],
}


def render_mcp_guidance(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    os_family: str | None = None,
) -> dict[str, Any]:
    clients = detect_ide_clients(environ=environ, home=home, os_family=os_family)
    client_guidance = [_client_guidance(client) for client in clients]
    return {
        "ok": True,
        "status": "mcp_guidance",
        "structured": True,
        "transport": "stdio",
        "command": COMMAND,
        "args": list(ARGS),
        "default_snippet": {"command": COMMAND, "args": list(ARGS)},
        "manual_copy_only": True,
        "manual_copy_wording": "Manual-copy only: paste this local stdio snippet into the MCP client yourself.",
        "embeds_host_port_by_default": False,
        "reads_saved_user_config_by_default": True,
        "config_written": False,
        "app_opened": False,
        "no_auto_config_write": True,
        "detected_clients": client_guidance,
        "client_guidance": client_guidance,
        "advanced_override_examples": _advanced_override_examples(),
        "opens_network_port": False,
        "raw_osc_available": False,
        "arbitrary_path_available": False,
        "shell_execution_available": False,
        "remote_mcp_available": False,
        "background_service_started": False,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _client_guidance(client: Mapping[str, Any]) -> dict[str, Any]:
    status = str(client["status"])
    client_id = str(client["client_id"])
    return {
        "client_id": client_id,
        "name": str(client["name"]),
        "detected": status == "detected",
        "status": status,
        "status_dot": client.get("status_dot", "green" if status == "detected" else "grey"),
        "status_indicator": "active_green" if status == "detected" else "inactive_grey",
        "config_mode": "manual_copy",
        "command": COMMAND,
        "args": list(ARGS),
        "embeds_host_port": False,
        "config_written": False,
        "app_opened": False,
        "next_steps": CLIENT_NEXT_STEPS.get(
            client_id,
            [
                "Open the MCP client settings yourself.",
                "Paste the local stdio snippet manually.",
            ],
        ),
    }


def _advanced_override_examples() -> list[dict[str, Any]]:
    return [
        {
            "label": "Advanced manual host override",
            "description": "Use only when you intentionally want the MCP server process to read a different console host from the environment.",
            "manual_only": True,
            "default": False,
            "config_mode": "manual_copy",
            "command": COMMAND,
            "args": list(ARGS),
            "env": {"M32_CONSOLE_HOST": "<console-host>"},
        },
        {
            "label": "Advanced manual port override",
            "description": "Use only when you intentionally want the MCP server process to read a non-default console port from the environment.",
            "manual_only": True,
            "default": False,
            "config_mode": "manual_copy",
            "command": COMMAND,
            "args": list(ARGS),
            "env": {"M32_CONSOLE_PORT": "10023"},
        },
    ]
