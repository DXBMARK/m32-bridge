from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


CLIENTS = (
    ("claude_desktop", "Claude Desktop"),
    ("codex", "Codex"),
    ("gemini", "Gemini"),
    ("antigravity", "Antigravity"),
    ("chatgpt_desktop", "ChatGPT Desktop"),
    ("vscode", "VS Code"),
    ("cursor", "Cursor"),
)


def detect_ide_clients(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    os_family: str | None = None,
) -> list[dict[str, object]]:
    env = dict(environ or os.environ)
    root = home or Path.home()
    family = os_family or _detect_os_family(env)
    hints = _client_hints(family, env, root)
    detected = []
    for client_id, label in CLIENTS:
        is_detected = any(_hint_detected(value) for value in hints[client_id])
        detected.append(
            {
                "client_id": client_id,
                "name": label,
                "status": "detected" if is_detected else "not_detected",
                "status_dot": "green" if is_detected else "grey",
                "writes_config": False,
                "opens_app": False,
                "requires_permission": False,
            }
        )
    return detected


def _detect_os_family(env: Mapping[str, str]) -> str:
    if env.get("WSL_DISTRO_NAME"):
        return "wsl"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def _client_hints(os_family: str, env: Mapping[str, str], root: Path) -> dict[str, list[object]]:
    common = {
        "claude_desktop": [env.get("CLAUDE_DESKTOP")],
        "codex": [env.get("CODEX_HOME"), root / ".codex"],
        "gemini": [env.get("GEMINI_HOME"), root / ".gemini"],
        "antigravity": [env.get("ANTIGRAVITY_HOME"), root / ".antigravity"],
        "chatgpt_desktop": [env.get("CHATGPT_DESKTOP")],
        "vscode": [env.get("VSCODE_CWD"), root / ".vscode"],
        "cursor": [env.get("CURSOR_TRACE_ID"), root / ".cursor"],
    }
    if os_family == "windows":
        local = Path(env.get("LOCALAPPDATA") or root / "AppData" / "Local")
        roaming = Path(env.get("APPDATA") or root / "AppData" / "Roaming")
        program_files = Path(env.get("ProgramFiles") or "C:/Program Files")
        common["claude_desktop"].extend([roaming / "Claude", local / "Claude"])
        common["chatgpt_desktop"].extend([local / "Programs" / "ChatGPT", roaming / "ChatGPT"])
        common["vscode"].extend([roaming / "Code", program_files / "Microsoft VS Code"])
        common["cursor"].extend([roaming / "Cursor", local / "Programs" / "Cursor"])
        common["gemini"].append(roaming / "Gemini")
        common["antigravity"].append(roaming / "Antigravity")
    elif os_family == "macos":
        apps = root / "Applications"
        support = root / "Library" / "Application Support"
        common["claude_desktop"].extend([support / "Claude", apps / "Claude.app"])
        common["chatgpt_desktop"].extend([support / "ChatGPT", apps / "ChatGPT.app"])
        common["vscode"].extend([support / "Code", apps / "Visual Studio Code.app"])
        common["cursor"].extend([support / "Cursor", apps / "Cursor.app"])
        common["gemini"].extend([support / "Gemini"])
        common["antigravity"].extend([support / "Antigravity"])
    else:
        config = root / ".config"
        common["claude_desktop"].extend([config / "Claude", config / "claude"])
        common["chatgpt_desktop"].extend([config / "ChatGPT", config / "chatgpt"])
        common["vscode"].extend([config / "Code", config / "code"])
        common["cursor"].extend([config / "Cursor", config / "cursor"])
        common["gemini"].extend([config / "gemini"])
        common["antigravity"].extend([config / "antigravity"])
    return common


def _hint_detected(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, Path):
        return value.exists()
    if isinstance(value, str):
        if not value:
            return False
        if "/" in value or "\\" in value:
            return Path(value).exists()
        return True
    return bool(value)
