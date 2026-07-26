"""Manual-copy local MCP host launch guidance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_mcp_launch_guidance(
    *,
    host_app: str,
    include_advanced_env_example: bool = False,
    host_config_path: Path | None = None,
) -> dict[str, Any]:
    snippet = {
        "m32-bridge": {
            "command": "m32-bridge",
            "args": ["mcp-server"],
        }
    }
    guidance: dict[str, Any] = {
        "host_app": host_app,
        "transport": "stdio",
        "command": "m32-bridge",
        "args": ["mcp-server"],
        "manual_copy_required": True,
        "embeds_host_port": False,
        "snippet": json.dumps(snippet, sort_keys=True),
        "advanced_env_override_example": None,
        "stdout_protocol_clean": True,
        "logs_to_stderr": True,
        "opens_network_port": False,
        "host_config_path": str(host_config_path) if host_config_path else None,
        "host_config_modified": False,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }
    if include_advanced_env_example:
        guidance["advanced_env_override_example"] = {
            "label": "Advanced manual environment override",
            "manual_only": True,
            "env": {
                "M32_CONSOLE_HOST": "<console-host>",
                "M32_CONSOLE_PORT": "10023",
            },
        }
    return guidance
