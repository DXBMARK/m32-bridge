from __future__ import annotations

import os
import platform as py_platform
import re
import select
import shutil
import socket
import ssl
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

from m32_bridge.runtime_preconditions import evaluate_console_precondition
from m32_bridge.installer.application_version import application_version
from m32_bridge.installer.display_safety import sanitize_display_value
from m32_bridge.installer.runtime_status import (
    RUNTIME_COMMAND_REGISTRY,
    RUNTIME_PICKER_ORDER,
    build_runtime_doctor,
    build_runtime_health,
    build_runtime_status,
    record_console_result,
)


BG_HEX = "#243947"
PRIMARY_HEX = "#F97E1A"
MUTED_SLATE_HEX = "#8BA2B5"
SUCCESS_HEX = "#2ECC71"
ACCENT_HEX = "#FFD25A"
BG_RGB = (36, 57, 71)
PRIMARY_RGB = (249, 126, 26)
MUTED_RGB = (139, 162, 181)
SUCCESS_RGB = (46, 204, 113)
ACCENT_RGB = (255, 210, 90)
ERROR_RGB = (255, 92, 92)
TEXT_RGB = (240, 244, 248)
PRODUCT_NAME = "X32-Bridge MCP"
INSTALLER_NAME = "X32-Bridge MCP Installer"
PACKAGE_NAME = "m32-mcp-bridge"
CLI_NAME = "m32-bridge"
BANNER = "X32-BRIDGE MCP INSTALLER"
RUNTIME_BANNER = "X32-BRIDGE MCP"
RUNTIME_SUBTITLE = "RUNTIME CONSOLE"
POWERED_BY = "Powered by DXBMARK LLC"
CONTACT_URL = "https://www.dxbmark.com"
CONTACT_EMAIL = "support@dxbmark.com"
CONTACT_PHONE = "+971505121583"
INSTALLER_SOURCE_USER_AGENT = "X32-Bridge-MCP-Installer"

DXBMARK_ASCII_LOGO = r"""
#  ______  ______  __  __    _    ____  _  __
# |  _ \ \/ / __ )|  \/  |  / \  |  _ \| |/ / LLC
# | | | \  /|  _ \| |\/| | / _ \ | |_) | ' /
# | |_| /  \| |_) | |  | |/ ___ \|  _ <| . \
# |____/_/\_\____/|_|  |_/_/   \_\_| \_\_|\_\ dxbmark.com
""".strip("\n")

def _command(
    desc: str,
    scope: str,
    shell: str,
    *,
    requires_console_config: bool = False,
    read_only: bool = True,
    setup_command: bool = False,
    safe_to_retry_after_setup: bool = False,
) -> dict[str, Any]:
    return {
        "desc": desc,
        "scope": scope,
        "shell": shell,
        "requires_console_config": requires_console_config,
        "read_only": read_only,
        "setup_command": setup_command,
        "safe_to_retry_after_setup": safe_to_retry_after_setup,
    }


COMMAND_REGISTRY = {
    "/health": _command("Check runtime and installation readiness", "local-only", "m32-bridge health"),
    "/setup": _command("Configure a known console endpoint", "network read-only; may save config", "m32-bridge setup", read_only=False, setup_command=True),
    "/get-info": _command("Read information from the configured endpoint", "network read-only", "m32-bridge get-info", requires_console_config=True, safe_to_retry_after_setup=True),
    "/verify-device": _command("Verify the configured endpoint; no network scan", "network read-only", "m32-bridge detect-device", requires_console_config=True, safe_to_retry_after_setup=True),
    "/doctor-runtime": _command("Diagnose local runtime issues", "local-only", "m32-bridge doctor-runtime"),
    "/mcp-config": _command("Generate safe MCP client configuration and setup guidance", "local-only", "m32-bridge mcp-config"),
    "/status": _command("Show runtime status", "local-only", "m32-bridge status"),
    "/contact": _command("Show product information, version, publisher and support", "local-only", "runtime-only"),
    "/help": _command("Show the responsive command guide", "local-only", "m32-bridge --help"),
    "/clear": _command("Clear and redraw the current screen", "local-only", "runtime-only"),
    "/exit": _command("Exit and restore the terminal", "local-only", "runtime-only"),
}
SHELL_ALIASES = {
    "m32-bridge health": "/health",
    "m32-bridge setup": "/setup",
    "m32-bridge get-info": "/get-info",
    "m32-bridge detect-device": "/verify-device",
    "m32-bridge doctor-runtime": "/doctor-runtime",
    "m32-bridge mcp-config": "/mcp-config",
    "m32-bridge status": "/status",
    "m32-bridge status --refresh": "/status refresh",
    "help": "/help",
    "status": "/status",
    "clear": "/clear",
    "contact": "/contact",
    "q": "/exit",
    "quit": "/exit",
    "exit": "/exit",
}
_PICKER_ORDER = (
    "/help",
    "/status",
    "/health",
    "/setup",
    "/get-info",
    "/verify-device",
    "/doctor-runtime",
    "/mcp-config",
    "/contact",
    "/clear",
    "/exit",
)
SLASH_COMMANDS = [
    {
        "cmd": command,
        "desc": COMMAND_REGISTRY[command]["desc"],
        "category": "Action" if command in {"/health", "/setup", "/get-info", "/verify-device", "/doctor-runtime"} else "Utility",
    }
    for command in _PICKER_ORDER
]
RUNTIME_SLASH_COMMANDS = [
    {
        "cmd": command,
        "desc": RUNTIME_COMMAND_REGISTRY[command].description,
        "category": "Action" if RUNTIME_COMMAND_REGISTRY[command].view not in {"help", "contact", "main", "exit"} else "Utility",
    }
    for command in RUNTIME_PICKER_ORDER
]
PANEL_VIEWS = frozenset({"help", "contact", "status", "health", "get_info", "verify_device", "doctor", "panel", "action", "setup", "mcp"})
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def is_tty(stdin: TextIO | None = None, stdout: TextIO | None = None) -> bool:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    return bool(stdin.isatty() and stdout.isatty())


def enable_windows_ansi(*, stream: TextIO | None = None) -> bool:
    if os.name != "nt" or not is_tty(stdout=stream or sys.stdout):
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        mode.value |= 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode))
    except Exception:
        os.system("")
        return False


class CRLFStdout:
    def __init__(self, real: TextIO):
        self.real = real

    def write(self, text: str) -> int:
        if "\n" in text:
            out: list[str] = []
            for ch in text:
                if ch == "\n" and (not out or out[-1] != "\r"):
                    out.append("\r")
                out.append(ch)
            text = "".join(out)
        return self.real.write(text)

    def flush(self) -> None:
        self.real.flush()

    def isatty(self) -> bool:
        return self.real.isatty()

    def fileno(self) -> int:
        return self.real.fileno()


class Colors:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        if enabled:
            self.RESET = "\x1b[0m"
            self.BG_DEFAULT = f"\x1b[48;2;{BG_RGB[0]};{BG_RGB[1]};{BG_RGB[2]}m"
            self.RESET_BG = f"{self.BG_DEFAULT}\x1b[38;2;{TEXT_RGB[0]};{TEXT_RGB[1]};{TEXT_RGB[2]}m"
            self.BOLD = "\x1b[1m"
            self.DIM = "\x1b[2m"
            self.TEXT = self._fg(TEXT_RGB)
            self.PRIMARY = self._fg(PRIMARY_RGB)
            self.SECONDARY = self._fg((255, 165, 60))
            self.ACCENT = self._fg(ACCENT_RGB)
            self.MUTED = self._fg(MUTED_RGB)
            self.SUCCESS = self._fg(SUCCESS_RGB)
            self.ERROR = self._fg(ERROR_RGB)
            self.BORDER = self.PRIMARY
            self.HIGHLIGHT = f"\x1b[48;2;{PRIMARY_RGB[0]};{PRIMARY_RGB[1]};{PRIMARY_RGB[2]}m\x1b[38;2;20;20;20m\x1b[1m"
        else:
            self.RESET = self.BG_DEFAULT = self.RESET_BG = self.BOLD = self.DIM = ""
            self.TEXT = self.PRIMARY = self.SECONDARY = self.ACCENT = self.MUTED = ""
            self.SUCCESS = self.ERROR = self.BORDER = self.HIGHLIGHT = ""

    def _fg(self, rgb: tuple[int, int, int]) -> str:
        return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{self.BG_DEFAULT}"


@dataclass
class TTYRow:
    kind: str
    text: str = ""
    label: str = ""
    value: Any = ""
    value_style: str = "normal"


@dataclass
class SetupState:
    field_index: int = 0
    values: dict[str, str] | None = None
    current_text: str = ""
    current_values: dict[str, str] | None = None
    source_by_field: dict[str, str] | None = None
    config_path: str | None = None
    target_type_index: int = 2
    configuration_unreadable: bool = False

    def __post_init__(self) -> None:
        if self.values is None:
            self.values = {}
        if self.current_values is None:
            self.current_values = {}
        if self.source_by_field is None:
            self.source_by_field = {}


SETUP_FIELDS = (
    ("host", "CONSOLE HOST", "required; no guessing or scan"),
    ("port", "Port", "10023"),
    ("label", "Label", "optional"),
    ("target_type", "Target type", "unknown"),
    ("confirmation", "Confirmation", "SAVE or CANCEL"),
)

TARGET_TYPE_OPTIONS = (
    ("hardware", "Physical M32 console"),
    ("emulator", "Emulator / test endpoint"),
    ("unknown", "Unknown / not declared"),
)
HELP_SECTIONS = {
    "INSTALLER HELP",
    "USAGE",
    "OPTIONS",
    "SYNTAX NOTES",
    "COMMANDS",
    "NAVIGATION",
    "CONFIGURATION",
    "SAFETY",
    "STATUS COLOURS",
    "FIELD GUIDE",
    "CONTACT",
    "X32-BRIDGE MCP",
    "PRODUCT",
    "PURPOSE",
    "CURRENT INSTALLER",
    "SAFETY MODEL",
    "POWERED BY",
    "MCP CLIENT SETUP",
    "INSTALLATION",
    "INSTALL SELECTION",
    "CONFIGURATION PRINCIPLE",
    "CLIENT COMPATIBILITY",
    "CLAUDE DESKTOP",
    "CODEX",
    "GEMINI CLI",
    "ANTIGRAVITY",
    "CHATGPT",
    "GENERIC MCP CLIENT",
    "SECURITY",
    "VERIFICATION CHECKLIST",
}


@dataclass
class SlashCommandPicker:
    commands: list[dict[str, str]]
    index: int = 0
    window_start: int = 0
    visible_limit: int = 7
    _last_query: str = ""

    def filtered(self, query: str) -> list[dict[str, str]]:
        query = query.lower()
        return [command for command in self.commands if command["cmd"].lower().startswith(query)]

    def move(self, query: str, direction: str) -> None:
        matches = self.filtered(query)
        if not matches:
            self.index = 0
            self.window_start = 0
            return
        if query != self._last_query and self._last_query:
            self.index = 0
            self.window_start = 0
            self._last_query = query
        elif query != self._last_query:
            self._last_query = query
        if direction == "UP":
            self.index = (self.index - 1) % len(matches)
        elif direction == "DOWN":
            self.index = (self.index + 1) % len(matches)
        self._keep_selection_visible(len(matches))

    def select(self, query: str) -> str | None:
        matches = self.filtered(query)
        if not matches:
            return None
        if query != self._last_query and self._last_query:
            self.index = 0
            self.window_start = 0
            self._last_query = query
        elif query != self._last_query:
            self._last_query = query
        self.index = min(self.index, len(matches) - 1)
        self._keep_selection_visible(len(matches))
        return matches[self.index]["cmd"]

    def render(self, query: str, colors: Colors) -> str:
        matches = self.filtered(query)
        if not matches:
            return ""
        if query != self._last_query and self._last_query:
            self.index = 0
            self.window_start = 0
            self._last_query = query
        elif query != self._last_query:
            self._last_query = query
        self.index = min(self.index, len(matches) - 1)
        self._keep_selection_visible(len(matches))
        limit = max(1, min(self.visible_limit, len(matches)))
        end = min(self.window_start + limit, len(matches))
        visible_matches = matches[self.window_start : end]
        border = "-" * 58
        lines = [f"{colors.BORDER}+-- Available Commands ({len(matches)}) {border[:31]}+{colors.RESET_BG}"]
        lines.append(f" Showing {self.window_start + 1}–{end} of {len(matches)}")
        if self.window_start:
            lines.append(f" ↑ {self.window_start} above")
        for idx, command in enumerate(visible_matches, start=self.window_start):
            selected = idx == self.index
            command_text = f"{command['cmd']:<13}"
            desc_text = f"{command['desc']:<42}"
            if selected:
                lines.append(f" {colors.HIGHLIGHT} > {command_text} {desc_text} {colors.RESET_BG}")
            else:
                lines.append(f"   {colors.PRIMARY}{command_text}{colors.RESET_BG} {colors.MUTED}{desc_text}{colors.RESET_BG}")
        remaining = len(matches) - end
        if remaining:
            lines.append(f" ↓ {remaining} more")
        lines.append(f"{colors.BORDER}+{border[:58]}+{colors.RESET_BG}")
        lines.append(f" {colors.MUTED}[Up/Down] Navigate | [Tab/Enter] Select | [ESC] Dismiss{colors.RESET_BG}")
        return "\n".join(lines)

    def _keep_selection_visible(self, total: int) -> None:
        limit = max(1, self.visible_limit)
        max_start = max(total - limit, 0)
        if self.index < self.window_start:
            self.window_start = self.index
        elif self.index >= self.window_start + limit:
            self.window_start = self.index - limit + 1
        self.window_start = min(max(self.window_start, 0), max_start)


def render_tty_installer(surface: str, result: dict[str, Any], *, dry_run: bool, color: bool = False) -> str:
    if color:
        return render_full_screen(surface, result, dry_run=dry_run, color=True)
    colors = Colors(False)
    body = [render_semantic_row(row, colors) for row in _body_rows(surface, result, dry_run=dry_run)]
    footer = render_footer_status(result, color=False)
    return "\n".join([_render_header(colors, tty_mode=str(result.get("tty_mode") or "installer")), "", *body, "", footer])


def terminal_size(size_provider: Any | None = None) -> tuple[int, int]:
    size = size_provider() if size_provider else shutil.get_terminal_size(fallback=(80, 24))
    width = max(int(getattr(size, "columns", size[0] if isinstance(size, tuple) else 80)), 20)
    height = max(int(getattr(size, "lines", size[1] if isinstance(size, tuple) else 24)), 8)
    return width, height


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def visible_width(text: str) -> int:
    return len(strip_ansi(text))


def truncate_ansi_safe(text: str, width: int) -> str:
    if width <= 0:
        return ""
    out: list[str] = []
    visible = 0
    pos = 0
    for match in ANSI_RE.finditer(text):
        segment = text[pos : match.start()]
        for ch in segment:
            if visible >= width:
                return "".join(out)
            out.append(ch)
            visible += 1
        out.append(match.group(0))
        pos = match.end()
    for ch in text[pos:]:
        if visible >= width:
            break
        out.append(ch)
        visible += 1
    return "".join(out)


def pad_ansi_line(text: str, width: int, *, color: bool = True) -> str:
    colors = Colors(color)
    truncated = truncate_ansi_safe(text, width)
    pad = max(width - visible_width(truncated), 0)
    return f"{colors.BG_DEFAULT}{truncated}{colors.BG_DEFAULT}{' ' * pad}"


def move_cursor(row: int, column: int) -> str:
    return f"\x1b[{max(row, 1)};{max(column, 1)}H"


def hide_cursor() -> str:
    return "\x1b[?25l"


def show_cursor() -> str:
    return "\x1b[?25h"


def clear_screen_with_background(*, color: bool = True) -> str:
    colors = Colors(color)
    return f"{colors.BG_DEFAULT}\x1b[2J\x1b[H" if color else ""


def reset_terminal() -> str:
    return "\x1b[r\x1b[?7h\x1b[?25h\x1b[0m\n"


def disable_autowrap() -> str:
    return "\x1b[?7l"


def enable_autowrap() -> str:
    return "\x1b[?7h"


def render_full_screen(
    surface: str,
    result: dict[str, Any],
    *,
    dry_run: bool,
    color: bool = True,
    width: int | None = None,
    height: int | None = None,
    panel_lines: list[str] | None = None,
    panel_offset: int = 0,
    input_buffer: str = "",
    picker: SlashCommandPicker | None = None,
    view: str = "main",
) -> str:
    width = width or terminal_size()[0]
    height = height or terminal_size()[1]
    header, body, footer = render_frame(
        surface,
        result,
        dry_run=dry_run,
        color=color,
        width=width,
        height=height,
        panel_lines=panel_lines,
        panel_offset=panel_offset,
        input_buffer=input_buffer,
        picker=picker,
        view=view,
    )
    rows = [*header, *body, footer]
    return render_frame_to_terminal(rows, color=color)


def render_frame_to_terminal(rows: list[str], *, color: bool) -> str:
    output = [clear_screen_with_background(color=color)]
    for row_number, row in enumerate(rows, start=1):
        output.append(move_cursor(row_number, 1))
        output.append(row)
    return "".join(output)


def render_frame(
    surface: str,
    result: dict[str, Any],
    *,
    dry_run: bool,
    color: bool,
    width: int,
    height: int,
    panel_lines: list[str] | None = None,
    panel_offset: int = 0,
    input_buffer: str = "",
    picker: SlashCommandPicker | None = None,
    view: str = "main",
) -> tuple[list[str], list[str], str]:
    colors = Colors(color)
    content_width = max(width - 1, 20)
    tty_mode = str(result.get("tty_mode") or "installer")
    if tty_mode == "runtime" and not isinstance(result.get("runtime_status_snapshot", {}).get("application"), dict):
        build_runtime_status(result, refresh=False)
    header_raw = _header_lines(colors, width=width, tty_mode=tty_mode)
    max_header = max(1, min(len(header_raw), max(height - 3, 1)))
    header = [pad_ansi_line(line, content_width, color=color) for line in header_raw[:max_header]]
    body_height = max(height - len(header) - 1, 0)
    prompt = "m32-bridge >" if tty_mode == "runtime" else "root/ $"
    command_text = f"{prompt} {input_buffer}" if input_buffer else f"{prompt} "
    overlay_lines: list[str] = []
    panel_footer: str | None = None
    if input_buffer.startswith("/"):
        command_height_for_picker = 1 if body_height else 0
        picker_available = max(body_height - command_height_for_picker, 1)
        available_commands = RUNTIME_SLASH_COMMANDS if tty_mode == "runtime" else SLASH_COMMANDS
        picker_text = _render_picker_overlay(input_buffer, picker or SlashCommandPicker(available_commands), colors, picker_available)
        overlay_lines = picker_text.splitlines() if picker_text else ["No matching commands"]
        view = "picker"
    elif panel_lines:
        view = view if view != "main" else "panel"
    footer = pad_ansi_line(
        render_footer_status(result, color=color, view=view, width=width),
        content_width,
        color=color,
    )
    main_rows = [render_semantic_row(row, colors) for row in _body_rows(surface, result, dry_run=dry_run, width=width, height=height)]
    command_height = 1 if body_height and (input_buffer or overlay_lines or panel_lines) else 0
    if panel_lines and view in PANEL_VIEWS:
        overlay_capacity = max(body_height - command_height, 0)
        overlay_lines, panel_footer = _panel_window(panel_lines, panel_offset, overlay_capacity, view=view)
        footer = pad_ansi_line(
            render_footer_status(result, color=color, view=view, width=width, panel_footer=panel_footer),
            content_width,
            color=color,
        )
    elif overlay_lines and view == "picker":
        overlay_capacity = len(overlay_lines)
    elif overlay_lines and view in PANEL_VIEWS:
        overlay_capacity = max(min(len(overlay_lines), max(body_height - command_height, 0)), 0)
    else:
        overlay_capacity = max(min(len(overlay_lines), max(body_height // 3, 3)), 0) if overlay_lines else 0
    main_capacity = max(body_height - command_height - overlay_capacity, 0)
    raw_body = main_rows[:main_capacity]
    while len(raw_body) < main_capacity:
        raw_body.append("")
    if overlay_capacity:
        raw_body.extend(overlay_lines[:overlay_capacity])
    if command_height:
        raw_body.append(command_text)
    body = [pad_ansi_line(line, content_width, color=color) for line in raw_body[:body_height]]
    while len(body) < body_height:
        body.append(pad_ansi_line("", content_width, color=color))
    return header, body, footer


def _picker_visible_limit(body_height: int, command_count: int) -> int:
    return max(3, min(7, max(body_height - 6, 3), command_count))


def _render_picker_overlay(query: str, picker: SlashCommandPicker, colors: Colors, available_rows: int) -> str:
    picker.visible_limit = min(_picker_visible_limit(available_rows + 1, len(picker.commands)), len(picker.filtered(query)) or len(picker.commands))
    text = picker.render(query, colors)
    while text and len(text.splitlines()) > available_rows and picker.visible_limit > 1:
        picker.visible_limit -= 1
        text = picker.render(query, colors)
    return text


def _panel_window(lines: list[str], offset: int, capacity: int, *, view: str) -> tuple[list[str], str]:
    if capacity <= 0:
        return [], ""
    total = len(lines)
    visible_capacity = max(capacity, 1)
    max_offset = max(total - visible_capacity, 0)
    offset = min(max(offset, 0), max_offset)
    end = min(offset + visible_capacity, total)
    window = lines[offset:end]
    if total <= visible_capacity:
        return window, "[ESC] Back"
    label = {
        "help": "help",
        "status": "status",
        "contact": "contact",
        "setup": "setup",
        "action": "result",
        "mcp": "MCP setup",
        "panel": "panel",
    }.get(view, "panel")
    if offset <= 0:
        footer = f"More below · Down/PgDn · Lines {offset + 1}–{end} of {total}"
    elif end >= total:
        footer = f"End of {label} · Up/PgUp to review · Lines {offset + 1}–{end} of {total}"
    else:
        footer = f"More above and below · Up/Down/PgUp/PgDn · Lines {offset + 1}–{end} of {total}"
    return window, footer


def render_semantic_row(row: TTYRow, colors: Colors) -> str:
    if row.kind == "blank":
        return ""
    if row.kind == "section":
        return f"{colors.PRIMARY}{colors.BOLD}{row.text}{colors.RESET_BG}"
    if row.kind == "field":
        safe_label = sanitize_display_value(row.label, max_length=64)
        safe_value = sanitize_display_value(row.value)
        if safe_label in _EQUALS_FIELDS:
            return f"  {colors.MUTED}{safe_label}{colors.RESET_BG}{colors.BORDER}={colors.RESET_BG}{_style_value(safe_value, row.value_style, colors)}"
        return f"  {colors.MUTED}{safe_label:<28}{colors.RESET_BG}{colors.BORDER}:{colors.RESET_BG} {_style_value(safe_value, row.value_style, colors)}"
    if row.kind == "text":
        return f"  {colors.TEXT}{sanitize_display_value(row.text)}{colors.RESET_BG}"
    if row.kind == "command":
        return f"  {colors.PRIMARY}{row.text}{colors.RESET_BG}"
    if row.kind == "warning":
        return f"  {colors.ACCENT}{row.text}{colors.RESET_BG}"
    if row.kind == "success":
        return f"  {colors.SUCCESS}{row.text}{colors.RESET_BG}"
    return row.text


def _style_value(value: str, style: str, colors: Colors) -> str:
    if style == "success":
        return f"{colors.SUCCESS}{value}{colors.RESET_BG}"
    if style == "warning":
        return f"{colors.ACCENT}{value}{colors.RESET_BG}"
    if style == "error":
        return f"{colors.ERROR}{value}{colors.RESET_BG}"
    if style == "command":
        return f"{colors.PRIMARY}{value}{colors.RESET_BG}"
    if style == "muted":
        return f"{colors.MUTED}{value}{colors.RESET_BG}"
    return f"{colors.TEXT}{value}{colors.RESET_BG}"


_EQUALS_FIELDS = {
    "user_local",
    "admin_required",
    "osc_writes_sent",
    "hardware_verified",
    "production_live_ready",
    "confirmation_required",
}


def render_status_text(result: dict[str, Any], *, color: bool = False) -> str:
    colors = Colors(color)
    from m32_bridge.installer.runtime_manager import inspect_runtime, platform_information
    from m32_bridge.runtime_preconditions import evaluate_console_precondition

    platform_info = result.get("platform_info") or platform_information()
    runtime = result.get("runtime_info") or inspect_runtime()
    source = result.setdefault(
        "source_status",
        {
            "network_https_route": "not_checked",
            "dns": "not_checked",
            "github_repository": "not_checked",
            "raw_installer": "not_checked",
            "source_archive": "not_checked",
            "last_checked": "not_checked",
        },
    )
    console_precondition = evaluate_console_precondition()
    console = console_precondition.resolution
    console_configured = console_precondition.state == "ready"
    console_invalid = console_precondition.state == "config_invalid"
    console_source = dict(console.source_by_field) if console is not None else {}
    console_label = console.effective_label if console_configured and console is not None else None
    console_target_type = console.effective_intended_target_type if console_configured and console is not None else "unknown"
    dry_run = bool(result.get("dry_run", result.get("status") in {"RUNTIME_SETUP_REQUIRED", "fresh_install"}))
    mode = "dry-run" if dry_run else "apply"
    mode_note = "Preview only; no install files are written." if dry_run else "User-local files may be written after confirmation."
    install_source = result.get("install_source") or "unknown"
    source_note = (
        "Running from local project files."
        if install_source == "local_checkout"
        else "Source is downloaded from the configured repository archive."
        if install_source == "github_release_or_archive"
        else "Check has not been run yet."
    )
    rows = [
        _section_title("INSTALLER STATUS", colors),
        _separator("=" * 60, colors),
        _section_title("INSTALLER", colors),
        _separator("-" * 60, colors),
        _status_field_colored("State", result.get("status"), _semantic_style_for_value(result.get("status")), colors),
        _status_field_colored("Mode", mode, "warning" if mode == "dry-run" else "success", colors),
        _status_field_colored("User-local", _bool(result.get("user_local", True)), "success", colors),
        _status_field_colored("Administrator", "not_required", "success", colors),
        _status_field_colored("Mode note", mode_note, "muted" if dry_run else "normal", colors),
        "",
        _section_title("PLATFORM", colors),
        _separator("-" * 60, colors),
        _status_field_colored("OS", platform_info.get("os"), "normal", colors),
        _status_field_colored("Version", platform_info.get("version"), "normal", colors),
        _status_field_colored("Kernel/build", platform_info.get("kernel_build"), "normal", colors),
        _status_field_colored("Architecture", platform_info.get("architecture"), "normal", colors),
        _status_field_colored("Shell", platform_info.get("shell"), "muted", colors),
        "",
        _section_title("RUNTIME", colors),
        _separator("-" * 60, colors),
        _status_field_colored("uv", "detected" if runtime.get("uv_detected") else "not_detected", "success" if runtime.get("uv_detected") else "muted", colors),
        _status_field_colored("uv version", _value_or(runtime, "uv_version", "not_detected"), _semantic_style_for_value(_value_or(runtime, "uv_version", "not_detected")), colors),
        _status_field_colored("uv path", _value_or(runtime, "uv_path", "not_detected"), "muted", colors),
        _status_field_colored("CPython", _value_or(runtime, "python_version", "not_detected"), _semantic_style_for_value(_value_or(runtime, "python_version", "not_detected")), colors),
        _status_field_colored("Python path", _value_or(runtime, "python_path", "not_detected"), "muted", colors),
        _status_field_colored("Frozen launcher", "enabled", "success", colors),
        _status_field_colored("Project range", runtime.get("project_required_range"), "normal", colors),
        _status_field_colored("System Python", "unchanged", "success", colors),
        "",
        _section_title("SOURCE", colors),
        _separator("-" * 60, colors),
        _status_field_colored("Install source", install_source, "normal", colors),
        _status_field_colored("Repository", _repository_url_from_source(str(result.get("source_url") or "")), "muted", colors),
        _status_field_colored("Network HTTPS route", source.get("network_https_route"), _semantic_style_for_value(source.get("network_https_route")), colors),
        _status_field_colored("DNS", source.get("dns"), _semantic_style_for_value(source.get("dns")), colors),
        _status_field_colored("GitHub repository", source.get("github_repository"), _semantic_style_for_value(source.get("github_repository")), colors),
        _status_field_colored("Raw installer", source.get("raw_installer"), _semantic_style_for_value(source.get("raw_installer")), colors),
        _status_field_colored("Source archive", source.get("source_archive"), _semantic_style_for_value(source.get("source_archive")), colors),
        _status_field_colored("Last checked", source.get("last_checked"), "muted", colors),
        _status_field_colored("Source ref", result.get("source_ref") or "not_configured", _semantic_style_for_value(result.get("source_ref") or "not_configured"), colors),
        _status_field_colored("Local source files", "available" if install_source == "local_checkout" else "not_checked", "success" if install_source == "local_checkout" else "muted", colors),
        _status_field_colored("Source note", source_note, "muted", colors),
        "",
        _section_title("CONSOLE CONFIGURATION", colors),
        _separator("-" * 60, colors),
        _status_field_colored("Configured", _bool(console_configured), "success" if console_configured else ("error" if console_invalid else "muted"), colors),
        _status_field_colored("Configuration state", console_precondition.state, "error" if console_invalid else ("success" if console_configured else "warning"), colors),
        _status_field_colored("Host", console_precondition.effective_host or "not_configured", "normal" if console_configured else "muted", colors),
        _status_field_colored("Port", console_precondition.effective_port or "not_configured", "normal" if console_configured else "muted", colors),
        _status_field_colored("Host source", render_config_source_name(console_source.get("host")), "muted", colors),
        _status_field_colored("Port source", render_config_source_name(console_source.get("port")), "muted", colors),
        _status_field_colored("Config file", _config_path_text(console_precondition.config_path), "muted", colors),
        _status_field_colored("Label", console_label or "not set", "normal" if console_label else "muted", colors),
        _status_field_colored("Intended target", display_target_type(console_target_type), "normal", colors),
        _status_field_colored(
            "Next action",
            "none" if console_configured else ("Repair the saved configuration or run /setup" if console_invalid else "Run /setup"),
            "muted" if console_configured else ("error" if console_invalid else "command"),
            colors,
        ),
        _status_field_colored("Connection verified", "no", "success", colors),
        _status_field_colored("Last connection state", result.get("console_connection_status") or "not_checked", _semantic_style_for_value(result.get("console_connection_status") or "not_checked"), colors),
        "  Saved configuration only. This is not device discovery.",
        "",
        _section_title("SAFETY", colors),
        _separator("-" * 60, colors),
        _status_field_colored("OSC writes sent", 0, "success", colors),
        _status_field_colored("/set", "not_sent", "success", colors),
        _status_field_colored("Network scan", "not_run", "success", colors),
        _status_field_colored("Admin elevation", "not_used", "success", colors),
        _status_field_colored("Hardware verified", "false", "success", colors),
        _status_field_colored("Production ready", "false", "success", colors),
        "",
        f"{colors.MUTED}End of status{colors.RESET_BG}",
    ]
    return "\n".join(rows)


def installer_help_text(*, color: bool = False, width: int = 80) -> str:
    colors = Colors(color)
    left = [
        "USAGE",
        "-" * 60,
        "  POSIX        sh scripts/install.sh [OPTIONS]",
        "  PowerShell   .\\scripts\\install.ps1 [OPTIONS]",
        "",
        "OPTIONS",
        "-" * 60,
        "  -h, --help",
        "  --dry-run",
        "  --json",
        "  --platform <name>",
        "  --version <vX.Y.Z>",
        "  --channel <stable|prerelease|main>",
        "  --ref <FULL_40_HEX_SHA>",
        "  --local",
        "  JSON mode is machine-readable and never prompts or installs.",
        "",
        "INSTALL SELECTION",
        "-" * 60,
        "  Standalone default : latest stable official Release",
        "  Checkout default   : local checkout",
        "  Specific Release   : --version vX.Y.Z",
        "  Prerelease         : --channel prerelease",
        "  Development main   : --channel main (explicit only)",
        "  Immutable commit   : --ref FULL_40_HEX_SHA",
        "",
        "SYNTAX NOTES",
        "-" * 60,
        "  [value] optional | <value> required | ... one or more values",
        "",
        "COMMANDS",
        "-" * 60,
        "  /help             Installer help",
        "  /health           Runtime readiness",
        "  /setup            Configure known endpoint",
        "  /get-info         Read /info",
        "  /verify-device    Verify configured endpoint (m32-bridge detect-device)",
        "  /doctor-runtime   Diagnose local runtime",
        "  /mcp-config       MCP client setup guidance",
        "  /status           Installer and source status",
        "  /contact          DXBMARK contact",
        "  /clear            Redraw screen",
        "  /exit             Exit installer",
        "",
        "NAVIGATION",
        "-" * 60,
        "  /             Open commands",
        "  Up/Down       Navigate picker",
        "  Enter/Tab     Select",
        "  ESC           Back or exit",
        "  PageUp/Down   Scroll long panels",
        "  q / quit / exit /exit",
    ]
    right = [
        "CONFIGURATION",
        "-" * 60,
        "  Resolved runtime configuration is the source of truth.",
        "  Saved endpoints are not discovered from this computer.",
        "  /status does not probe the console.",
        "",
        "SAFETY",
        "-" * 60,
        "  No scan",
        "  No OSC writes",
        "  No /set",
        "  No admin",
        "  No system Python modification",
        "",
        "STATUS COLOURS",
        "-" * 60,
        "  Green   Available, successful, or safety requirement satisfied",
        "  Yellow  Attention, confirmation, or user action required",
        "  Red     Failure or blocker",
        "  Slate   Information or not checked",
        "",
        "FIELD GUIDE",
        "-" * 60,
        "  Console IP     Known address only; setup will not guess or scan",
        "  Port           Default 10023",
        "  Save           SAVE stores configuration first, then verifies with /info",
        "  Label          Local name stored only by M32 Bridge",
        "  Intended target Operator expectation, not verification",
        "  Saved config   User-local runtime.yaml unless overridden by command/env",
        "  Shell alias    /verify-device maps to m32-bridge detect-device",
        "",
        "CONTACT",
        f"  {CONTACT_URL}",
        f"  {CONTACT_EMAIL}",
        f"  {CONTACT_PHONE}",
    ]
    if width >= 100:
        content = _split_columns(left, right, width, colors)
    elif width >= 60:
        content = [_style_help_line(line, colors) for line in _fit_plain_lines([*left, "", *right], width)]
    else:
        content = [_style_help_line(line, colors) for line in _fit_plain_lines(_compact_help_lines(), width)]
    return "\n".join([_style_help_line("INSTALLER HELP", colors), _style_help_line("=" * 60, colors), *content, "", f"{colors.MUTED}End of help{colors.RESET_BG}"])


def installer_contact_text(*, color: bool = False, width: int | None = None) -> str:
    colors = Colors(color)
    terminal_width = width or terminal_size()[0]
    lines = [
        "X32-BRIDGE MCP",
        "=" * 60,
        "",
        "PRODUCT",
        "-" * 60,
        f"  Application            : {PRODUCT_NAME}",
        f"  Installer              : {INSTALLER_NAME}",
        f"  Version                : {application_version()}",
        f"  Package                : {PACKAGE_NAME}",
        f"  CLI                    : {CLI_NAME}",
        "  Publisher              : DXBMARK LLC",
        "",
        "PURPOSE",
        "-" * 60,
        "  A local safety-first MCP bridge for Midas M32 and",
        "  X32-family digital consoles using OSC.",
        "",
        "  It allows supported AI/MCP hosts to inspect console state,",
        "  analyse routing and processing, and prepare controlled",
        "  recommendations through a local operator-managed bridge.",
        "",
        "CURRENT INSTALLER",
        "-" * 60,
        "  Configures the local managed Python runtime.",
        "  Installs user-local application and launcher files.",
        "  Stores the known console endpoint.",
        "  Provides health, status, diagnostics and read-only",
        "  connection verification.",
        "",
        "SAFETY MODEL",
        "-" * 60,
        "  Local MCP transport     : stdio",
        "  Network scan            : not used",
        "  OSC writes during setup : 0",
        "  /set during setup       : not sent",
        "  Administrator access    : not required",
        "  System Python           : unchanged",
        "  Hardware verification   : separate from operator intent",
        "",
        "POWERED BY",
        "-" * 60,
        "  DXBMARK LLC",
        f"  Website                 : {CONTACT_URL}",
        f"  Support                 : {CONTACT_EMAIL}",
        f"  Phone / WhatsApp        : {CONTACT_PHONE}",
        "",
        "End of product information",
    ]
    fitted = _fit_plain_lines(lines, max(min(terminal_width - 2, 100), 30))
    return "\n".join(_style_help_line(line, colors) for line in fitted)


def parse_installer_command(command: str) -> str | None:
    normalized = " ".join(command.strip().split())
    lowered = normalized.lower()
    if not lowered:
        return ""
    if any(token in normalized for token in ("|", ">", "<", ";", "&&", "||", "$(", "`", "\n", "\r")):
        return None
    if lowered == "/":
        return "/"
    if lowered in COMMAND_REGISTRY:
        return lowered
    if lowered == "/status refresh":
        return lowered
    return SHELL_ALIASES.get(lowered)


def parse_runtime_command(command: str) -> str | None:
    normalized = " ".join(command.strip().split())
    lowered = normalized.lower()
    if not lowered:
        return ""
    if any(token in normalized for token in ("|", ">", "<", ";", "&&", "||", "$(", "`", "\n", "\r")):
        return None
    if lowered == "/":
        return "/"
    if lowered in RUNTIME_COMMAND_REGISTRY:
        return lowered
    aliases = {
        "help": "/help",
        "m32-bridge --help": "/help",
        "status": "/status",
        "status refresh": "/status refresh",
        "m32-bridge status": "/status",
        "m32-bridge status --refresh": "/status refresh",
        "m32-bridge health": "/health",
        "m32-bridge setup": "/setup",
        "m32-bridge get-info": "/get-info",
        "m32-bridge detect-device": "/verify-device",
        "m32-bridge doctor-runtime": "/doctor-runtime",
        "m32-bridge mcp-config": "/mcp-config",
        "clear": "/clear",
        "contact": "/contact",
        "q": "/exit",
        "quit": "/exit",
        "exit": "/exit",
    }
    return aliases.get(lowered)


def runtime_handler_ids() -> frozenset[str]:
    return frozenset(_runtime_handlers())


def dispatch_runtime_command(
    command: str,
    result: dict[str, Any],
    *,
    color: bool = False,
    input_func: Callable[[str], str] | None = None,
    width: int | None = None,
    handlers: dict[str, Callable[..., tuple[str, bool]]] | None = None,
) -> tuple[str, bool]:
    action = parse_runtime_command(command)
    if action is None:
        return "Unknown command. Type / to view allowed commands.", False
    if action == "":
        return "", False
    if action == "/":
        return render_runtime_command_picker("/", color=color), False
    spec = RUNTIME_COMMAND_REGISTRY.get(action)
    if spec is None:
        return "Unknown command. Type / to view allowed commands.", False
    handler = (handlers or _runtime_handlers()).get(spec.handler_id)
    if handler is None:
        return render_runtime_command_failure("COMMAND_FAILED", log_path=None, color=color), False
    result.setdefault("_runtime_handler_trace", []).append(spec.handler_id)
    return handler(result, color=color, input_func=input_func, width=width)


def _runtime_handlers() -> dict[str, Callable[..., tuple[str, bool]]]:
    return {
        "runtime_help": _runtime_handle_help,
        "runtime_status": _runtime_handle_status,
        "runtime_status_refresh": _runtime_handle_status_refresh,
        "runtime_health": _runtime_handle_health,
        "runtime_setup": _runtime_handle_setup,
        "runtime_get_info": _runtime_handle_get_info,
        "runtime_verify_device": _runtime_handle_verify_device,
        "runtime_doctor": _runtime_handle_doctor,
        "runtime_mcp_config": _runtime_handle_mcp_config,
        "runtime_contact": _runtime_handle_contact,
        "runtime_clear": _runtime_handle_clear,
        "runtime_exit": _runtime_handle_exit,
    }


def _runtime_handle_help(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    return runtime_help_text(color=bool(kwargs.get("color"))), False


def _runtime_handle_status(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    payload = build_runtime_status(result, refresh=False)
    return render_runtime_status_panel(payload, color=bool(kwargs.get("color"))), False


def _runtime_handle_status_refresh(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    payload = build_runtime_status(result, refresh=True)
    return render_runtime_status_panel(payload, color=bool(kwargs.get("color"))), False


def _runtime_handle_health(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    payload = build_runtime_health(result)
    return render_runtime_health_panel(payload, color=bool(kwargs.get("color"))), False


def _runtime_handle_setup(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    input_func = kwargs.get("input_func")
    if input_func is None:
        return _setup_view_text(), False
    return _execute_setup(input_func, result, color=bool(kwargs.get("color"))), False


def _runtime_handle_get_info(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    return _execute_console_read("/get-info", result, color=bool(kwargs.get("color"))), False


def _runtime_handle_verify_device(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    return _execute_console_read("/verify-device", result, color=bool(kwargs.get("color"))), False


def _runtime_handle_doctor(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    return render_doctor_runtime_panel(build_runtime_doctor(result), color=bool(kwargs.get("color"))), False


def _runtime_handle_mcp_config(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance, render_mcp_guidance_text

    payload = render_mcp_guidance(environ=dict(os.environ), version=application_version())
    payload["network_scan"] = "not_run"
    return _style_panel_text(render_mcp_guidance_text(payload, width=kwargs.get("width") or terminal_size()[0]), color=bool(kwargs.get("color"))), False


def _runtime_handle_contact(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    return runtime_contact_text(result=result, color=bool(kwargs.get("color"))), False


def _runtime_handle_clear(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    surface = "windows" if str(result.get("platform", "")).startswith("windows") else "posix"
    return render_tty_installer(surface, result, dry_run=False, color=bool(kwargs.get("color"))), False


def _runtime_handle_exit(result: dict[str, Any], **kwargs: Any) -> tuple[str, bool]:
    return "Runtime Console exited.", True


def execute_installer_command(
    command: str,
    result: dict[str, Any],
    *,
    color: bool = False,
    input_func: Callable[[str], str] | None = None,
    width: int | None = None,
) -> tuple[str, bool]:
    try:
        return _execute_command_impl(
            command,
            result,
            color=color,
            input_func=input_func,
            width=width,
        )
    except Exception as exc:
        if result.get("tty_mode") != "runtime":
            raise
        from .runtime_faults import write_runtime_diagnostic_log

        error_code = _classify_runtime_exception(exc)
        log_path = None
        if error_code == "COMMAND_FAILED":
            app_path = Path(str(result.get("app_path") or Path.home() / ".m32-bridge" / "app"))
            try:
                log_path = write_runtime_diagnostic_log(app_path.parent / "logs", exc)
            except Exception:
                log_path = None
        return render_runtime_command_failure(error_code, log_path=log_path, color=color), False


def _execute_command_impl(
    command: str,
    result: dict[str, Any],
    *,
    color: bool = False,
    input_func: Callable[[str], str] | None = None,
    width: int | None = None,
) -> tuple[str, bool]:
    if result.get("tty_mode") == "runtime":
        return dispatch_runtime_command(
            command,
            result,
            color=color,
            input_func=input_func,
            width=width,
        )
    action = parse_installer_command(command)
    if action is None:
        return "Unknown command. Type / to view allowed commands.", False
    if action in {"", None}:
        return "", False
    if action == "/":
        return render_command_picker("/", color=color), False
    if action == "/help":
        if result.get("tty_mode") == "runtime":
            return runtime_help_text(color=color), False
        return installer_help_text(color=color, width=width or terminal_size()[0]), False
    if action == "/contact":
        if result.get("tty_mode") == "runtime":
            return runtime_contact_text(result=result, color=color), False
        return installer_contact_text(color=color, width=width), False
    if action == "/mcp-config":
        from m32_bridge.installer.mcp_guidance import render_mcp_guidance, render_mcp_guidance_text

        payload = render_mcp_guidance(environ=dict(os.environ), version=application_version())
        return _style_panel_text(render_mcp_guidance_text(payload, width=width or terminal_size()[0]), color=color), False
    if action == "/status":
        if result.get("tty_mode") == "runtime":
            return render_runtime_health_panel(result, color=color), False
        return render_status_text(result, color=color), False
    if action == "/status refresh":
        if result.get("tty_mode") == "runtime":
            return render_runtime_health_panel(result, color=color), False
        refresh_source_status(result, force=True)
        return render_status_text(result, color=color), False
    if action == "/clear":
        surface = "windows" if str(result.get("platform", "")).startswith("windows") else "posix"
        return render_tty_installer(surface, result, dry_run=bool(result.get("dry_run", True)), color=color), False
    if action == "/exit":
        message = "Runtime Console exited." if result.get("tty_mode") == "runtime" else "Installer exited. No dependency or console write action was taken."
        return message, True
    if action == "/health":
        if result.get("tty_mode") == "runtime":
            return render_runtime_health_panel(result, color=color), False
        from m32_bridge.cli import health

        payload = health()
        payload.update(
            {
                "runtime": _local_runtime_payload(result),
                "osc_writes_sent": 0,
                "network_scan": "not_run",
                "console_probe": "not_run",
            }
        )
        return render_health_panel(payload, color=color), False
    if action == "/doctor-runtime":
        return render_doctor_runtime_panel(_local_runtime_payload(result), color=color), False
    if action == "/setup":
        if input_func is None:
            return _setup_view_text(), False
        return _execute_setup(input_func, result, color=color), False
    if action in {"/get-info", "/verify-device"}:
        return _execute_console_read(action, result, color=color), False
    return "Unknown command. Type / to view allowed commands.", False


def refresh_source_status(
    result: dict[str, Any],
    *,
    checker: Callable[[str, float], str] | None = None,
    force: bool = False,
    timeout: float = 1.5,
) -> dict[str, str]:
    cached = result.get("source_status")
    if not force and isinstance(cached, dict) and cached.get("last_checked") not in {None, "not_checked"}:
        return cached
    if result.get("_source_refresh_in_progress"):
        existing = result.get("source_status")
        if isinstance(existing, dict):
            return existing
        return {
            "network_https_route": "not_checked",
            "dns": "not_checked",
            "github_repository": "not_checked",
            "raw_installer": "not_checked",
            "source_archive": "not_checked",
            "last_checked": "not_checked",
        }
    result["_source_refresh_in_progress"] = True
    check = checker or _bounded_url_status
    refresh_urls = _source_refresh_urls_for_result(result)
    if refresh_urls is None:
        statuses = {
            "network_https_route": "not_checked",
            "dns": "not_checked",
            "github_repository": "not_checked",
            "raw_installer": "not_checked",
            "source_archive": "not_checked",
            "last_checked": "not_run_source_identity_unavailable",
        }
        result["source_status"] = statuses
        result["_source_refresh_in_progress"] = False
        return statuses
    raw_url, archive_url = refresh_urls
    try:
        network_https_route = check("https://github.com/", timeout)
        github_repository = check("https://github.com/DXBMARK/m32-bridge", timeout)
        raw_installer = check(raw_url, timeout)
        source_archive = check(archive_url, timeout)
        statuses = {
            "network_https_route": network_https_route,
            "dns": derive_dns_status([network_https_route, github_repository, raw_installer, source_archive]),
            "github_repository": github_repository,
            "raw_installer": raw_installer,
            "source_archive": source_archive,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
        result["source_status"] = statuses
        return statuses
    finally:
        result["_source_refresh_in_progress"] = False


def _execute_setup(input_func: Callable[[str], str], result: dict[str, Any], *, color: bool = False) -> str:
    host = input_func("Known console host: ").strip()
    if not host:
        return "Run /setup with a known console IP. No host was guessed and no scan was run."
    port_text = input_func("Port [10023]: ").strip()
    label = input_func("Label [optional]: ").strip() or None
    target_type = input_func("Target type [unknown]: ").strip() or "unknown"
    confirmation = input_func("Type SAVE to store config and verify, or CANCEL: ").strip()
    return _execute_setup_payload(
        result,
        host=host,
        port_text=port_text,
        label=label,
        target_type=target_type,
        confirmation=confirmation,
        color=color,
    )


def _execute_setup_payload(
    result: dict[str, Any],
    *,
    host: str,
    port_text: str,
    label: str | None,
    target_type: str,
    confirmation: str,
    color: bool = False,
) -> str:
    try:
        port = int(port_text) if port_text else 10023
    except ValueError:
        return "Invalid port. Enter a value from 1 to 65535."
    if port < 1 or port > 65535:
        return "Invalid port. Enter a value from 1 to 65535."
    action = confirmation.strip().upper()
    if action != "SAVE":
        return render_setup_result_panel(
            {
                "ok": False,
                "status": "CANCELLED" if action == "CANCEL" else "CONFIRMATION_REQUIRED",
                "message": "Setup cancelled. Existing configuration was not changed." if action == "CANCEL" else "Type SAVE to store this configuration or CANCEL to discard it.",
                "configured_host": host,
                "configured_port": port,
                "attempted_path": "not_attempted",
                "intended_path": "/info",
                "verification_attempted": False,
                "legacy_installer_probe_not_run": result.get("tty_mode") != "runtime",
                "console_probe": "not_run",
                "network_scan": "not_run",
                "config_not_written": True,
                "scan_attempted": False,
                "osc_writes_sent": 0,
                "hardware_verified": False,
                "production_live_ready": False,
            },
            color=color,
        )
    from m32_bridge.cli import setup_runtime
    from m32_bridge.config.runtime import default_user_config_path, resolve_runtime_config

    resolution = resolve_runtime_config(cli_args={}, environ=dict(os.environ), allow_project_local=False)
    resolved_config_path = resolution.config_path or default_user_config_path()

    payload = setup_runtime(
        host=host,
        port=port,
        target_type=canonical_target_type(target_type),
        label=label,
        save=True,
        confirm_save=True,
        config_path=Path(resolved_config_path),
    )
    payload["configured_host"] = host
    payload["configured_port"] = port
    payload["config_path"] = str(resolved_config_path)
    payload["intended_target_type"] = canonical_target_type(target_type)
    payload["scan_attempted"] = False
    payload["network_scan"] = "not_run"
    payload["osc_writes_sent"] = 0
    payload["verification_attempted"] = payload.get("attempted_path") == "/info"
    payload["console_probe"] = "run" if payload["verification_attempted"] else "not_run"
    payload["connection_state"] = "reachable" if payload.get("connected") else ("unreachable" if payload["verification_attempted"] else "not_checked")
    payload["endpoint_verified"] = bool(payload.get("connected"))
    if payload["verification_attempted"] and not payload.get("connected"):
        payload["verification_status"] = _classify_runtime_payload_failure(payload)
        payload["error_code"] = payload["verification_status"]
    record_console_result(result, payload)
    build_runtime_status(result, refresh=False)
    return render_setup_result_panel(payload, color=color)


def _execute_console_read(action: str, result: dict[str, Any], *, color: bool = False) -> str:
    precondition = evaluate_console_precondition()
    if precondition.state == "config_invalid":
        return render_runtime_command_failure("CONFIG_INVALID", log_path=None, color=color)
    if precondition.state == "setup_required":
        return render_setup_required_panel(action, color=color)
    resolution = precondition.resolution
    if resolution is None:
        return render_runtime_command_failure("CONFIG_INVALID", log_path=None, color=color)
    get_info_runtime, detect_device_runtime = _load_console_command_handlers()
    if action == "/get-info":
        payload = get_info_runtime(host=resolution.effective_host, port=resolution.effective_port)
        title = "GET INFO"
    else:
        payload = detect_device_runtime(
            host=resolution.effective_host,
            port=resolution.effective_port,
            target_type=resolution.effective_intended_target_type or "unknown",
        )
        title = "VERIFY DEVICE"
        result["device_verification_status"] = payload.get("classification") or payload.get("status")
    payload["source_by_field"] = dict(resolution.source_by_field)
    payload["config_path"] = str(resolution.config_path) if resolution.config_path else None
    payload["label"] = resolution.effective_label
    payload["intended_target_type"] = resolution.effective_intended_target_type or "unknown"
    payload["configured_host"] = resolution.effective_host
    payload["configured_port"] = resolution.effective_port
    payload["scan_attempted"] = False
    payload["network_scan"] = "not_run"
    payload["console_probe"] = "run"
    payload["osc_writes_sent"] = 0
    payload["hardware_verified"] = bool(payload.get("hardware_verified") is True and payload.get("classification") == "HARDWARE_VERIFIED")
    payload["production_live_ready"] = False
    if result.get("tty_mode") == "runtime" and not payload.get("connected"):
        runtime_error = _classify_runtime_payload_failure(payload)
        payload["error_code"] = runtime_error
        payload["status"] = runtime_error
    payload["connection_state"] = "reachable" if payload.get("connected") else "unreachable"
    payload["next_action"] = (
        "none"
        if payload.get("connected")
        else "Check console power, configured IP, UDP port, and network route."
    )
    record_console_result(result, payload)
    build_runtime_status(result, refresh=False)
    if action == "/get-info":
        return render_get_info_panel(payload, color=color)
    return render_verify_device_panel(payload, color=color)


def _load_console_command_handlers() -> tuple[Callable[..., dict[str, Any]], Callable[..., dict[str, Any]]]:
    from m32_bridge.cli import detect_device_runtime, get_info_runtime

    return get_info_runtime, detect_device_runtime


def render_setup_required_panel(command: str, *, allow_setup_chain: bool = True, color: bool = False) -> str:
    return _panel(
        "SETUP REQUIRED",
        [
            (
                "PRECONDITION",
                [
                    ("Error code", "SETUP_REQUIRED", "warning"),
                    ("Command", command, "command"),
                    ("Attempted path", "not_attempted", "success"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("Console probe", "not_run", "success"),
                    ("Network scan", "not_run", "success"),
                    ("OSC writes", 0, "success"),
                ],
            ),
        ],
        notes=(
            [
                "A console endpoint has not been configured.",
                f"Run /setup before using {command}.",
                "Press Enter to start setup or ESC to cancel.",
            ]
            if allow_setup_chain
            else [
                "A console endpoint has not been configured.",
                f"Run /setup before using {command}.",
                "This command is not eligible for automatic retry after setup.",
            ]
        ),
        color=color,
    )


def _classify_runtime_exception(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if isinstance(exc, TimeoutError) or "timeout" in text:
        return "CONNECTION_TIMEOUT"
    if isinstance(exc, ConnectionRefusedError) or "connection refused" in text:
        return "CONNECTION_REFUSED"
    if isinstance(exc, socket.gaierror) or "name resolution" in text or "getaddrinfo" in text:
        return "DNS_RESOLUTION_FAILED"
    if "device" in text and "respond" in text:
        return "DEVICE_NOT_RESPONDING"
    if "config" in text and "not found" in text:
        return "CONFIG_NOT_FOUND"
    if "config" in text and "invalid" in text:
        return "CONFIG_INVALID"
    return "COMMAND_FAILED"


def _classify_runtime_payload_failure(payload: dict[str, Any]) -> str:
    text = " ".join(
        str(payload.get(key) or "")
        for key in ("error_code", "status", "exception_type", "message")
    ).lower()
    if "timeout" in text:
        return "CONNECTION_TIMEOUT"
    if "refused" in text:
        return "CONNECTION_REFUSED"
    if "dns" in text or "gaierror" in text or "name resolution" in text:
        return "DNS_RESOLUTION_FAILED"
    return "DEVICE_NOT_RESPONDING"


def render_runtime_command_failure(error_code: str, *, log_path: Path | None, color: bool = False) -> str:
    rows = [("Error code", error_code, "warning" if error_code != "COMMAND_FAILED" else "error")]
    if error_code == "COMMAND_FAILED":
        rows.append(("Diagnostic log", str(log_path) if log_path is not None else "unavailable", "muted"))
    return _panel(
        "COMMAND ERROR",
        [("RESULT", rows), ("SAFETY", [("OSC writes", 0, "success"), ("Network scan", "not_run", "success")])],
        notes=["The command could not be completed. Runtime Console is still available."],
        color=color,
    )


def _local_runtime_payload(result: dict[str, Any]) -> dict[str, Any]:
    from m32_bridge.installer.runtime_manager import local_runtime_diagnostics, platform_information

    return local_runtime_diagnostics(
        app_path=result.get("app_path"),
        launcher_path=result.get("launcher_path"),
    )


def _setup_view_text() -> str:
    return "\n".join(
        [
            "SETUP",
            "  Requires a console host you already know.",
            "  Default port: 10023",
            "  SAVE stores the configuration first, then runs one read-only /info verification.",
            "  CANCEL or any other confirmation performs no network activity",
            "  No guessing. No subnet scan. No OSC writes.",
        ]
    )


def runtime_help_text(*, color: bool = False) -> str:
    colors = Colors(color)
    lines = [
        _section_title("RUNTIME CONSOLE HELP", colors),
        _separator("=" * 60, colors),
        "",
        _section_title("COMMANDS", colors),
        _separator("-" * 60, colors),
    ]
    for command in RUNTIME_PICKER_ORDER:
        metadata = RUNTIME_COMMAND_REGISTRY[command]
        lines.extend(
            [
                f"  {colors.PRIMARY}{command}{colors.RESET_BG}",
                f"    Purpose : {metadata.description}",
                f"    Network : {metadata.network_scope}",
                f"    Setup   : {'required' if metadata.requires_console_config else 'not required'}",
                f"    Writes  : {'may save runtime config' if not metadata.read_only else 'none'}",
                f"    Shell   : {metadata.shell_equivalent}",
            ]
        )
    lines.extend(
        [
            "",
            _section_title("SAFETY", colors),
            _separator("-" * 60, colors),
            "  Commands requiring a console endpoint stop at SETUP_REQUIRED.",
            "  No host guessing, network scan, or OSC writes are performed.",
            "",
            f"{colors.MUTED}End of Runtime Console help{colors.RESET_BG}",
        ]
    )
    return "\n".join(lines)


def runtime_contact_text(*, result: dict[str, Any] | None = None, color: bool = False) -> str:
    snapshot = build_runtime_status(result, refresh=False)
    return _panel(
        "CONTACT",
        [
            ("PRODUCT", [("Name", PRODUCT_NAME, "normal"), ("Version", snapshot["application"]["version"], "normal"), ("Publisher", "DXBMARK LLC", "normal")]),
            ("SUPPORT", [("Website", CONTACT_URL, "muted"), ("Email", CONTACT_EMAIL, "muted"), ("Phone / WhatsApp", CONTACT_PHONE, "muted")]),
        ],
        notes=["Runtime support and product information."],
        color=color,
    )


def _setup_state_lines(state: SetupState, *, color: bool = False) -> list[str]:
    colors = Colors(color)
    values = state.values or {}
    current_values = state.current_values or {}
    current_key, current_label, hint = SETUP_FIELDS[state.field_index]
    step = state.field_index + 1
    if current_key == "confirmation":
        final_values = _setup_candidate_values(state)
        return [
            f"{colors.PRIMARY}{colors.BOLD}REVIEW SETUP{colors.RESET_BG}                                      {colors.ACCENT}Step {step}/5{colors.RESET_BG}",
            _separator("=" * 60, colors),
            "",
            _section_title("CONFIG FILE", colors),
            f"  {_config_path_text(state.config_path)}",
            "",
            _section_title("CHANGES", colors),
            _separator("-" * 60, colors),
            "  Console IP",
            _status_field_colored("Current", current_values.get("host") or "not configured", "muted", colors),
            _status_field_colored("New", _change_text(current_values.get("host"), final_values.get("host")), "normal", colors),
            "",
            "  OSC port",
            _status_field_colored("Current", current_values.get("port") or "not configured", "muted", colors),
            _status_field_colored("New", _change_text(current_values.get("port"), final_values.get("port")), "normal", colors),
            "",
            "  Label",
            _status_field_colored("Current", current_values.get("label") or "not set", "muted", colors),
            _status_field_colored("New", _change_text(current_values.get("label"), final_values.get("label") or "not set"), "normal", colors),
            "",
            "  Intended target",
            _status_field_colored("Current", display_target_type(current_values.get("target_type")), "muted", colors),
            _status_field_colored("New", _change_text(display_target_type(current_values.get("target_type")), display_target_type(final_values.get("target_type"))), "normal", colors),
            "",
            _section_title("SAVE BEHAVIOUR", colors),
            _separator("-" * 60, colors),
            "  1. Save the candidate configuration atomically to the user config.",
            "  2. Reload and verify the saved values.",
            "  3. Send one read-only /info request to the saved endpoint.",
            "  4. Keep the saved configuration even if the endpoint is offline.",
            "  5. Perform no OSC write, /set, scan, admin action, or system change.",
            "",
            f"> Type {colors.ACCENT}SAVE{colors.RESET_BG} to continue or {colors.MUTED}CANCEL{colors.RESET_BG} to return: {colors.TEXT}{state.current_text}_{colors.RESET_BG}",
            "",
            "Enter  Confirm · Backspace  Edit · ESC  Cancel",
        ]
    lines = [
        f"{colors.PRIMARY}{colors.BOLD}SETUP CONSOLE{colors.RESET_BG}                                     {colors.ACCENT}Step {step}/5{colors.RESET_BG}",
        _separator("=" * 60, colors),
        "",
        (
            "Existing configuration is unreadable. Enter safe replacement values."
            if state.configuration_unreadable
            else ("Existing configuration found" if current_values.get("host") else "No existing console endpoint is configured.")
        ),
        "",
        _status_field_colored("Config file", _config_path_text(state.config_path), "muted", colors),
        _status_field_colored("Host source", render_config_source_name((state.source_by_field or {}).get("host")), "muted", colors),
        _status_field_colored("Port source", render_config_source_name((state.source_by_field or {}).get("port")), "muted", colors),
        "",
    ]
    for key, label, default in SETUP_FIELDS:
        if key == "confirmation":
            continue
        marker = ">" if key == current_key else " "
        if key == "target_type":
            selected_value = _target_type_from_index(state.target_type_index)
            summary_value = display_target_type(selected_value)
            label_text = f"{colors.PRIMARY}{label:<20}{colors.RESET_BG}" if key == current_key else f"{colors.MUTED}{label:<20}{colors.RESET_BG}"
            lines.append(f"{marker} {label_text}: {_style_value(summary_value, 'normal' if key == current_key else 'muted', colors)}")
            if key == current_key:
                lines.append(_status_field_colored("Current value", display_target_type(current_value), "muted", colors))
                lines.append("")
                lines.append(f"  {colors.MUTED}TARGET TYPE [?]{colors.RESET_BG}")
                for index, (canonical, display) in enumerate(TARGET_TYPE_OPTIONS, start=1):
                    pointer = ">" if canonical == selected_value else " "
                    style = "command" if canonical == selected_value else "muted"
                    lines.append(f"  {pointer} {index}. {_style_value(display, style, colors)}")
                lines.extend(_setup_tooltip_lines(key))
            continue
        value = state.current_text if key == current_key else values.get(key, "")
        current_value = current_values.get(key)
        if key == "host" and not value:
            value = ""
        elif not value:
            value = f"{default} (placeholder)"
        suffix = "_" if key == current_key else ""
        label_text = f"{colors.PRIMARY}{label:<20}{colors.RESET_BG}" if key == current_key else f"{colors.MUTED}{label:<20}{colors.RESET_BG}"
        value_style = "normal" if key == current_key else "muted" if "(placeholder)" in str(value) else "normal"
        lines.append(f"{marker} {label_text}: {_style_value(str(value) + suffix, value_style, colors)}")
        if key == current_key:
            lines.append(_status_field_colored("Current value", display_target_type(current_value) if key == "target_type" else current_value or "not configured", "muted", colors))
            lines.extend(_setup_tooltip_lines(key))
    lines.extend(["", _separator("-" * 60, colors), f"Current field: {current_label} ({hint})", "Enter  Next · Backspace  Edit · ESC  Cancel"])
    return lines


def _setup_tooltip_lines(key: str) -> list[str]:
    if key == "host":
        return [
            "  The network address configured on the M32 console itself.",
            "  Do not enter this computer's IP address.",
            "  The installer does not scan or guess addresses.",
            "  Example: 192.168.8.120",
            "  Press Enter to keep the current value.",
        ]
    if key == "port":
        return [
            "  UDP port used by the M32 OSC protocol.",
            "  Default: 10023. Change it only if your console explicitly uses another port.",
            "  Press Enter to keep the current value.",
        ]
    if key == "label":
        return [
            "  Optional local name stored only by M32 Bridge.",
            "  Examples: FOH Console, Studio M32, Main Desk.",
            "  Type CLEAR to remove an existing label.",
        ]
    if key == "target_type":
        return [
            "  Up/Down moves selection. Enter accepts the highlighted value.",
            "  Keys 1, 2, and 3 select directly.",
            "  This is operator intent, not device verification.",
        ]
    return []


def _setup_candidate_values(state: SetupState) -> dict[str, str]:
    current = state.current_values or {}
    values = state.values or {}
    label_value = values.get("label", current.get("label", ""))
    if str(label_value).strip().upper() == "CLEAR":
        label_value = ""
    return {
        "host": values.get("host") or current.get("host", ""),
        "port": values.get("port") or current.get("port", "10023"),
        "label": label_value,
        "target_type": canonical_target_type(values.get("target_type") or _target_type_from_index(state.target_type_index) or current.get("target_type", "unknown")),
    }


def _change_text(current: str | None, new: str | None) -> str:
    current_text = current or ""
    new_text = new or ""
    if current_text == new_text:
        return "unchanged"
    return new_text or "cleared"


def _advance_setup_state(state: SetupState, result: dict[str, Any], *, color: bool = False) -> tuple[str | None, bool]:
    key = SETUP_FIELDS[state.field_index][0]
    value = state.current_text.strip()
    current_value = (state.current_values or {}).get(key, "")
    if key == "target_type":
        state.values = state.values or {}
        state.values[key] = canonical_target_type(value) if value and canonical_target_type(value) in {"hardware", "emulator", "unknown"} else _target_type_from_index(state.target_type_index)
        state.current_text = ""
        if state.field_index < len(SETUP_FIELDS) - 1:
            state.field_index += 1
            return None, False
    if key == "host" and not value and not current_value:
        return "Host is required. No host was guessed and no scan was run.", False
    if key != "target_type":
        state.values = state.values or {}
        if value:
            state.values[key] = value
        elif key in {"host", "port", "label"} and current_value:
            state.values[key] = current_value
        state.current_text = ""
        if state.field_index < len(SETUP_FIELDS) - 1:
            state.field_index += 1
            return None, False
    candidates = _setup_candidate_values(state)
    confirmation = state.values.get("confirmation", "").strip()
    action = confirmation.upper()
    if action not in {"SAVE", "CANCEL"}:
        state.field_index = len(SETUP_FIELDS) - 1
        state.current_text = confirmation
        return "Type SAVE to store this configuration or CANCEL to discard it.", False
    output = _execute_setup_payload(
        result,
        host=candidates.get("host", ""),
        port_text=candidates.get("port", ""),
        label=candidates.get("label") or None,
        target_type=candidates.get("target_type") or "unknown",
        confirmation=action,
        color=color,
    )
    return output, True


def _panel(
    title: str,
    sections: list[tuple[str, list[tuple[str, Any, str]]]],
    *,
    notes: list[str] | None = None,
    color: bool = False,
) -> str:
    colors = Colors(color)
    lines = [_section_title(title, colors), _separator("=" * 60, colors)]
    for section, rows in sections:
        lines.extend(["", _section_title(section, colors), _separator("-" * 60, colors)])
        for label, value, style in rows:
            safe_label = sanitize_display_value(label, max_length=64)
            rendered = sanitize_display_value(_human_value(value))
            if len(rendered) > 70 and "/" in rendered:
                lines.append(f"  {colors.MUTED}{safe_label:<26}{colors.RESET_BG}:")
                lines.append(f"    {_style_value(rendered, style, colors)}")
            else:
                lines.append(_status_field_colored(safe_label, rendered, style, colors))
    if notes:
        lines.extend(["", _section_title("RESULT", colors), _separator("-" * 60, colors)])
        lines.extend(f"  {_style_value(sanitize_display_value(note), _semantic_style_for_value(note), colors)}" for note in notes)
    lines.append("")
    lines.append(f"{colors.MUTED}End of {title.lower()}{colors.RESET_BG}")
    return "\n".join(lines)


def render_health_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    ok = bool(payload.get("ok", payload.get("status") in {"ok", "healthy", "OK"}))
    status = "OK" if ok else "ACTION REQUIRED"
    return _panel(
        "HEALTH",
        [
            ("OVERALL", [("Status", status, "success" if ok else "warning")]),
            (
                "RUNTIME",
                [
                    ("uv", "detected" if runtime.get("uv_detected") else _value_or(payload, "uv"), "success" if runtime.get("uv_detected") else "muted"),
                    ("CPython", _value_or(runtime, "python_version", "not_detected"), "normal"),
                    ("Managed runtime", "ready" if runtime.get("managed_python_detected") else "action required", "success" if runtime.get("managed_python_detected") else "warning"),
                    ("Frozen execution", "enabled", "success"),
                    ("App files", _value_or(runtime, "app_files", _value_or(runtime, "app_path_status")), _semantic_style_for_value(_value_or(runtime, "app_files", _value_or(runtime, "app_path_status")))),
                    ("Launcher", _value_or(runtime, "launcher_executable", _value_or(runtime, "launcher_status")), _semantic_style_for_value(_value_or(runtime, "launcher_executable", _value_or(runtime, "launcher_status")))),
                ],
            ),
            (
                "CONSOLE",
                [
                    ("Endpoint configured", _bool(bool(payload.get("host") or payload.get("configured_host"))), "normal"),
                    ("Probe performed", "no", "success"),
                    ("Hardware verified", "no", "success"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("OSC writes", payload.get("osc_writes_sent", 0), "success"),
                    ("Network scan", "not run", "success"),
                    ("Administrator", "not used", "success"),
                    ("System Python", "unchanged", "success"),
                ],
            ),
        ],
        notes=[payload.get("message") or ("Local runtime is healthy." if ok else "Review required actions in /status.")],
        color=color,
    )


def render_runtime_health_panel(result: dict[str, Any], *, color: bool = False) -> str:
    payload = result if "configuration_readiness" in result else build_runtime_health(result)
    application = payload["application"]
    readiness = payload["configuration_readiness"]
    connection = payload["last_known_connection"]
    safety = payload["safety"]
    return _panel(
        "HEALTH",
        [
            (
                "APPLICATION",
                [
                    ("Application runtime", application["application_runtime"], _semantic_style_for_value(application["application_runtime"])),
                    ("Managed Python", application["managed_python"], _semantic_style_for_value(application["managed_python"])),
                    ("Required imports", application["required_imports"], _semantic_style_for_value(application["required_imports"])),
                    ("Frozen launcher", application["frozen_launcher"], "success"),
                    ("App files", application["app_files"], _semantic_style_for_value(application["app_files"])),
                    ("Launcher executable", _bool(application["launcher_executable"]), "success" if application["launcher_executable"] else "warning"),
                ],
            ),
            (
                "CONFIGURATION READINESS",
                [
                    ("Configuration state", readiness["configuration_state"], _semantic_style_for_value(readiness["configuration_state"])),
                    ("Console configured", _bool(readiness["console_configured"]), "success" if readiness["console_configured"] else "warning"),
                    ("Operational state", readiness["operational_state"], _semantic_style_for_value(readiness["operational_state"])),
                    ("Next action", readiness["next_action"], "muted" if readiness["next_action"] == "none" else "command"),
                ],
            ),
            (
                "LAST KNOWN CONNECTION",
                [
                    ("Connection state", connection["connection_state"], _semantic_style_for_value(connection["connection_state"])),
                    ("Last check", connection["last_check_at"], "muted"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("Attempted path", safety["attempted_path"], "success"),
                    ("Console probe", safety["console_probe"], "success"),
                    ("Console network scan", safety["network_scan"], "success"),
                    ("OSC writes", safety["osc_writes_sent"], "success"),
                ],
            ),
        ],
        notes=["Local application health only. No source refresh or console probe was run."],
        color=color,
    )


def render_runtime_status_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    application = payload["application"]
    platform_info = payload["platform"]
    runtime = payload["python_runtime"]
    source = payload["installation_source"]
    connectivity = payload["source_connectivity"]
    config = payload["console_configuration"]
    connection = payload["console_connection"]
    safety = payload["safety"]
    return _panel(
        "RUNTIME STATUS",
        [
            (
                "APPLICATION",
                [
                    ("Product", application["product"], "normal"),
                    ("Version", application["version"], "normal"),
                    ("Version source", application["version_source"], "normal"),
                    ("Version status", application["version_status"], _semantic_style_for_value(application["version_status"])),
                    ("App path", application["app_path"], "muted"),
                    ("Launcher path", application["launcher_path"], "muted"),
                    ("Runtime provenance", application["runtime_provenance"], "muted"),
                    ("Install metadata", application["install_metadata_status"], _semantic_style_for_value(application["install_metadata_status"])),
                ],
            ),
            (
                "PLATFORM",
                [
                    ("OS", platform_info.get("os") or "unknown", "normal"),
                    ("OS version", platform_info.get("version") or "unknown", "normal"),
                    ("Kernel / build", platform_info.get("kernel_build") or "unknown", "muted"),
                    ("Architecture", platform_info.get("architecture") or "unknown", "normal"),
                    ("Shell", platform_info.get("shell") or "unknown", "normal"),
                    ("Container", platform_info.get("container_hint") or "not_applicable", "muted"),
                    ("WSL", platform_info.get("wsl") or "not_applicable", "muted"),
                ],
            ),
            (
                "PYTHON RUNTIME",
                [
                    ("uv detected", _bool(runtime["uv_detected"]), "success" if runtime["uv_detected"] else "warning"),
                    ("uv version", runtime["uv_version"], "normal"),
                    ("uv path", runtime["uv_path"], "muted"),
                    ("Managed CPython", runtime["managed_python_version"], "normal"),
                    ("Managed Python path", runtime["managed_python_path"], "muted"),
                    ("Python source", runtime["python_source"], "normal"),
                    ("Approved minor", runtime["approved_minor"], "success"),
                    ("Project range", runtime["project_required_range"], "normal"),
                    ("Frozen launcher", runtime["frozen_launcher"], "success"),
                    ("System Python version", runtime["system_python_version"], "muted"),
                    ("System Python path", runtime["system_python_path"], "muted"),
                    ("System Python used", _bool(runtime["system_python_used"]), "success"),
                    ("System Python modified", _bool(runtime["system_python_modified"]), "success"),
                ],
            ),
            (
                "INSTALLATION SOURCE",
                [
                    ("Application version", source["application_version"], "normal"),
                    ("Application version source", source["application_version_source"], "normal"),
                    ("Requested selection", source["requested_selection"], "normal"),
                    ("Release channel", source["release_channel"], "normal"),
                    ("Release tag", source["release_tag"], "normal"),
                    ("Source commit", source["source_commit"], "normal"),
                    ("Source ref", source["source_ref"], "normal"),
                    ("Install source", source["install_source"], "normal"),
                    ("Repository", source["repository_url"], "muted"),
                    ("Installed at", source["installed_at"], "muted"),
                    ("Raw bootstrap URL", source["raw_installer_url"], "muted"),
                    ("Source archive URL", source["source_archive_url"], "muted"),
                    ("Manifest status", source["manifest_status"], _semantic_style_for_value(source["manifest_status"])),
                    ("Archive checksum", source["archive_checksum_status"], _semantic_style_for_value(source["archive_checksum_status"])),
                    ("Last source check", source["last_source_check"], "muted"),
                ],
            ),
            (
                "SOURCE CONNECTIVITY",
                [
                    ("Network HTTPS route", connectivity["network_https_route"], _semantic_style_for_value(connectivity["network_https_route"])),
                    ("DNS", connectivity["dns"], _semantic_style_for_value(connectivity["dns"])),
                    ("GitHub repository", connectivity["github_repository"], _semantic_style_for_value(connectivity["github_repository"])),
                    ("Raw bootstrap", connectivity["raw_installer"], _semantic_style_for_value(connectivity["raw_installer"])),
                    ("Source archive", connectivity["source_archive"], _semantic_style_for_value(connectivity["source_archive"])),
                ],
            ),
            (
                "CONSOLE CONFIGURATION",
                [
                    ("Configuration state", config["configuration_state"], _semantic_style_for_value(config["configuration_state"])),
                    ("Host", config["host"], "normal"),
                    ("Port", config["port"], "normal"),
                    ("Host source", render_config_source_name(config["host_source"]), "muted"),
                    ("Port source", render_config_source_name(config["port_source"]), "muted"),
                    ("Config file", _config_path_text(config["config_file"]), "muted"),
                    ("Label", config["label"], "normal"),
                    ("Intended target", display_target_type(config["intended_target"]), "normal"),
                ],
            ),
            (
                "CONSOLE CONNECTION",
                [
                    ("Connection state", connection["connection_state"], _semantic_style_for_value(connection["connection_state"])),
                    ("Last attempted path", connection["last_attempted_path"], "normal"),
                    ("Last error code", connection["last_error_code"], "muted"),
                    ("Last latency", connection["last_latency_ms"], "muted"),
                    ("Last check", connection["last_check_at"], "muted"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("OSC writes sent", safety["osc_writes_sent"], "success"),
                    ("/set", safety["set_command"], "success"),
                    ("Console network scan", safety["network_scan"], "success"),
                    ("Internet source refresh", safety["internet_source_refresh"], "success"),
                    ("Console probe", safety["console_probe"], "success"),
                    ("Admin elevation", safety["admin_elevation"], "success"),
                    ("System Python modified", _bool(safety["system_python_modified"]), "success"),
                    ("Hardware verified", _bool(safety["hardware_verified"]), "success"),
                    ("Production ready", _bool(safety["production_live_ready"]), "success"),
                ],
            ),
        ],
        notes=["Full local and cached Runtime status. Console connection is never probed by this command."],
        color=color,
    )


def render_doctor_runtime_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    if "runtime" not in payload or "installation" not in payload:
        return _render_legacy_doctor_runtime_panel(payload, color=color)
    runtime = payload["runtime"]
    installation = payload["installation"]
    policy = payload["policy"]
    safety = payload["safety"]
    imports = payload["required_imports"]
    return _panel(
        "DOCTOR RUNTIME",
        [
            (
                "RUNTIME",
                [
                    ("uv", "detected" if runtime["uv_detected"] else "not_detected", "success" if runtime["uv_detected"] else "warning"),
                    ("uv version", runtime["uv_version"], "normal"),
                    ("uv path", runtime["uv_path"], "muted"),
                    ("Managed CPython", runtime["managed_python_version"], "normal"),
                    ("Managed Python path", runtime["managed_python_path"], "muted"),
                    ("Approved Python", policy["approved_python"], "success"),
                    ("Project range", policy["project_required_range"], "normal"),
                ],
            ),
            ("REQUIRED IMPORTS", [(name, value.get("status", "not_available") if isinstance(value, dict) else value, "success" if isinstance(value, dict) and value.get("status") == "available" else "error") for name, value in imports.items()]),
            (
                "INSTALLATION",
                [
                    ("App files", installation["app_files"], _semantic_style_for_value(installation["app_files"])),
                    ("Launcher file", installation["launcher_file"], _semantic_style_for_value(installation["launcher_file"])),
                    ("Launcher executable", _bool(installation["launcher_executable"]), "success" if installation["launcher_executable"] else "warning"),
                    ("PATH visibility", _bool(installation["path_visibility"]), "success" if installation["path_visibility"] else "warning"),
                    ("Install metadata", installation["install_metadata_readability"], _semantic_style_for_value(installation["install_metadata_readability"])),
                    ("Config readability", installation["config_readability"], _semantic_style_for_value(installation["config_readability"])),
                    ("Log directory writable", _bool(installation["log_directory_writable"]), "success" if installation["log_directory_writable"] else "warning"),
                ],
            ),
            (
                "POLICY",
                [
                    ("Current user only", "true", "success"),
                    ("Admin elevation", policy["admin_elevation"], "success"),
                    ("System Python used", _bool(policy["system_python_used"]), "success"),
                    ("System Python modified", _bool(policy["system_python_modified"]), "success"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("Attempted path", safety["attempted_path"], "success"),
                    ("Console probe", safety["console_probe"], "success"),
                    ("Internet refresh", safety["internet_source_refresh"], "success"),
                    ("Network scan", safety["network_scan"], "success"),
                    ("OSC writes", safety["osc_writes_sent"], "success"),
                ],
            ),
        ],
        notes=["Deep local diagnostics completed without console or internet access."],
        color=color,
    )


def _render_legacy_doctor_runtime_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    healthy = bool(payload.get("ok") is True or str(payload.get("status", "")).lower() in {"ok", "healthy", "ready", "passed"})
    return _panel(
        "DOCTOR RUNTIME",
        [
            ("RUNTIME", [("uv", "detected" if payload.get("uv_detected") else "not_detected", "normal"), ("uv version", _value_or(payload, "uv_version", "not_detected"), "normal"), ("CPython", _value_or(payload, "python_version", "not_detected"), "normal")]),
            (
                "INSTALLATION",
                [
                    ("App files", _value_or(payload, "app_files", "not_checked"), "normal"),
                    ("Launcher file", _value_or(payload, "launcher_file", "not_checked"), "normal"),
                    ("Launcher executable", _value_or(payload, "launcher_executable", "not_checked"), "normal"),
                    ("PATH visibility", _value_or(payload, "path_visibility", "not_checked"), "normal"),
                ],
            ),
            ("SAFETY", [("Console probe", "not_run", "success"), ("Network scan", "not_run", "success"), ("OSC writes", 0, "success")]),
        ],
        notes=["Healthy" if healthy else "Runtime diagnostics completed; review action-required fields."],
        color=color,
    )


def render_get_info_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    connected = bool(payload.get("connected"))
    sources = payload.get("source_by_field") if isinstance(payload.get("source_by_field"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return _panel(
        "CONSOLE INFORMATION",
        [
            (
                "CONFIGURED ENDPOINT",
                [
                    ("Host", payload.get("configured_host") or payload.get("host") or "not_configured", "normal"),
                    ("Port", payload.get("configured_port") or payload.get("port") or "10023", "normal"),
                    ("Host source", render_config_source_name(sources.get("host")), "muted"),
                    ("Port source", render_config_source_name(sources.get("port")), "muted"),
                    ("Config file", _config_path_text(payload.get("config_path")), "muted"),
                    ("Label", payload.get("label") or "not set", "normal" if payload.get("label") else "muted"),
                    ("Intended target", display_target_type(payload.get("intended_target_type")), "normal"),
                ],
            ),
            (
                "CONNECTION RESULT",
                [
                    ("Attempted path", payload.get("attempted_path") or "/info", "normal"),
                    ("Connected", connected, "success" if connected else "error"),
                    ("Response", payload.get("status") or ("CONNECTED" if connected else "NOT_CONNECTED"), "success" if connected else "error"),
                    ("Latency", payload.get("latency_ms") if payload.get("latency_ms") is not None else (payload.get("latency") if payload.get("latency") is not None else "not_available"), "normal"),
                    ("Error code", payload.get("error_code") or "none", "muted" if connected else "error"),
                    ("Connection state", payload.get("connection_state") or ("reachable" if connected else "unreachable"), "success" if connected else "error"),
                    ("Next action", payload.get("next_action") or "none", "muted" if connected else "command"),
                ],
            ),
            (
                "DEVICE",
                [
                    ("Model", data.get("model") or payload.get("model") or "unavailable", "normal" if connected else "muted"),
                    ("Firmware", data.get("firmware") or payload.get("firmware") or payload.get("firmware_version") or "unavailable", "normal" if connected else "muted"),
                    ("Name", data.get("name") or payload.get("name") or payload.get("device_name") or "unavailable", "normal" if connected else "muted"),
                    ("Observed target", payload.get("classification") if connected else "unknown", "normal" if connected else "muted"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("OSC writes", payload.get("osc_writes_sent", 0), "success"),
                    ("Network scan", payload.get("network_scan", "not_run"), "success"),
                ],
            ),
        ],
        notes=[
            payload.get("message") or ("Read-only /info completed." if connected else "The configured endpoint did not respond to /info."),
            "This address came from saved configuration and was not discovered.",
        ],
        color=color,
    )


def render_verify_device_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    connected = bool(payload.get("connected"))
    hardware_verified = bool(payload.get("hardware_verified") is True and payload.get("classification") == "HARDWARE_VERIFIED")
    sources = payload.get("source_by_field") if isinstance(payload.get("source_by_field"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    intended = payload.get("intended_target_type") or "unknown"
    return _panel(
        "DEVICE VERIFICATION",
        [
            (
                "CONFIGURED INTENT",
                [
                    ("Intended target", display_target_type(intended), "normal"),
                    ("Configured endpoint", payload.get("endpoint") or f"{payload.get('configured_host') or payload.get('host', 'configured')}:{payload.get('configured_port') or payload.get('port', 10023)}", "normal"),
                    ("Config source", render_config_source_name(sources.get("intended_target_type") or sources.get("host")), "muted"),
                ],
            ),
            (
                "OBSERVED CONNECTION",
                [
                    ("Connected", _bool(connected), "success" if connected else "warning"),
                    ("Response", payload.get("status") or "unavailable", "success" if connected else "warning"),
                    ("Latency", payload.get("latency_ms") if payload.get("latency_ms") is not None else (payload.get("latency") if payload.get("latency") is not None else "not_available"), "normal"),
                    ("Observed target", payload.get("observed_target_type") or "unknown", "normal" if connected else "muted"),
                    ("Model", data.get("model") or payload.get("model") or "unavailable", "normal" if connected else "muted"),
                    ("Firmware", data.get("firmware") or payload.get("firmware") or payload.get("firmware_version") or "unavailable", "normal" if connected else "muted"),
                    ("Name", data.get("name") or payload.get("name") or payload.get("device_name") or "unavailable", "normal" if connected else "muted"),
                ],
            ),
            (
                "VERIFICATION",
                [
                    ("Classification", payload.get("classification") or "unavailable", "normal"),
                    ("Hardware verified", _bool(hardware_verified), "success"),
                    ("Production ready", "false", "success"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("Read-only path", payload.get("attempted_path") or "/info", "success"),
                    ("OSC writes", payload.get("osc_writes_sent", 0), "success"),
                    ("Network scan", payload.get("network_scan", "not_run"), "success"),
                ],
            ),
        ],
        notes=[
            "Intended target describes operator expectation only.",
            "It is not proof of hardware identity.",
        ],
        color=color,
    )


def render_setup_result_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    saved = bool(payload.get("config_saved") or payload.get("saved"))
    connected = bool(payload.get("connected"))
    endpoint_verified = bool(payload.get("endpoint_verified", connected))
    config_rows = [
        ("Saved", _bool(saved), "success" if saved else "warning"),
        ("Config file", _config_path_text(payload.get("config_path")), "muted"),
        ("Host", payload.get("configured_host") or payload.get("host") or "not_available", "normal"),
        ("Port", payload.get("configured_port") or payload.get("port") or "10023", "normal"),
        ("Persistence verified", _bool(payload.get("persistence_verified", False)), "success" if payload.get("persistence_verified") else "warning"),
    ]
    if not saved:
        config_rows.append(("Config not written", _bool(payload.get("config_not_written", True)), "success"))
    notes = _setup_result_notes(payload, saved=saved, connected=connected)
    verification_rows = [
        ("Read-only verification attempted", _bool(payload.get("verification_attempted", False)), "success"),
        ("Attempted path", payload.get("attempted_path") or "not_attempted", "normal"),
        ("Connection state", payload.get("connection_state") or ("reachable" if connected else "not_checked"), "success" if connected else "warning"),
        ("Endpoint verified", _bool(endpoint_verified), "success" if endpoint_verified else "warning"),
        ("Response", payload.get("response") or ("received" if connected else payload.get("verification_status") or payload.get("error_code") or payload.get("status") or "not_run"), "normal"),
        ("Classification", payload.get("classification") or "not_observed", "normal" if connected else "muted"),
    ]
    if payload.get("legacy_installer_probe_not_run") is True:
        verification_rows.insert(2, ("Intended path", payload.get("intended_path") or "/info", "normal"))
        verification_rows.append(("Probe not run", "true", "success"))
    return _panel(
        "SETUP RESULT",
        [
            (
                "CONFIGURATION",
                config_rows,
            ),
            (
                "CONNECTION VERIFICATION",
                verification_rows,
            ),
            (
                "SAFETY",
                [
                    ("OSC writes", payload.get("osc_writes_sent", 0), "success"),
                    ("Network scan", "not run", "success"),
                    ("Hardware verified", _bool(payload.get("hardware_verified", False)), "success"),
                    ("Production ready", _bool(payload.get("production_live_ready", False)), "success"),
                ],
            ),
        ],
        notes=notes,
        color=color,
    )


def _setup_result_notes(payload: dict[str, Any], *, saved: bool, connected: bool) -> list[str]:
    if str(payload.get("status")) == "CONFIG_WRITE_FAILED":
        return [payload.get("message") or "Runtime configuration could not be saved."]
    if saved and connected:
        return ["Configuration was saved successfully.", "Read-only endpoint verification completed."]
    if saved:
        return [
            "Configuration was saved successfully.",
            "The endpoint is currently unavailable or did not respond.",
            "Run /get-info or /verify-device when the console is online.",
        ]
    return [payload.get("message") or "No config was written."]


def _human_value(value: Any) -> str:
    if isinstance(value, bool):
        return _bool(value)
    if value is None:
        return "not_available"
    return str(value)


def _value_or(payload: dict[str, Any], key: str, fallback: Any = "not_checked") -> Any:
    return payload[key] if key in payload else fallback


def _status_field(label: str, value: Any) -> str:
    return f"  {sanitize_display_value(label, max_length=64):<26}: {sanitize_display_value(_human_value(value))}"


def _status_field_colored(label: str, value: Any, style: str, colors: Colors) -> str:
    rendered = sanitize_display_value(_human_value(value))
    safe_label = sanitize_display_value(label, max_length=64)
    return f"  {colors.MUTED}{safe_label:<26}{colors.RESET_BG}: {_style_value(rendered, style, colors)}"


def _separator(text: str, colors: Colors) -> str:
    return f"{colors.BORDER}{text}{colors.RESET_BG}"


def _section_title(text: str, colors: Colors) -> str:
    return f"{colors.PRIMARY}{colors.BOLD}{text}{colors.RESET_BG}"


def _style_panel_text(text: str, *, color: bool = False) -> str:
    colors = Colors(color)
    return "\n".join(_style_help_line(line, colors) for line in text.splitlines())


def _semantic_style_for_value(value: Any) -> str:
    text = _human_value(value).lower()
    if text in {"reachable", "resolved", "detected", "enabled", "ready", "ok", "healthy", "passed", "true"}:
        return "success"
    if text == "false":
        return "success"
    if text in {"not_checked", "not_determined", "not_available", "not_detected", "not_configured", "unknown"}:
        return "muted"
    if text in {"timeout", "unreachable", "dns_error", "tls_error", "http_error", "failed", "error"}:
        return "error"
    if "action" in text or "required" in text or "missing" in text:
        return "warning"
    if text in {"not_run", "not_sent", "not_used", "not_required", "unchanged"}:
        return "success"
    return "normal"


def _help_command_lines() -> list[str]:
    lines: list[str] = []
    for command, metadata in COMMAND_REGISTRY.items():
        lines.append(f"  {command:<16} {metadata['desc']}")
        lines.append(f"    Scope: {metadata['scope']}")
        lines.append(f"    Shell: {metadata['shell']}")
    return lines


def _help_command_detail_lines() -> list[str]:
    details: list[str] = []
    for command, metadata in COMMAND_REGISTRY.items():
        details.extend(
            [
                command,
                f"  Purpose : {metadata['desc']}",
                f"  Network : {metadata['scope']}",
                f"  Writes  : {'may save config after SAVE' if command == '/setup' else 'none'}",
                f"  Shell   : {metadata['shell']}",
            ]
        )
        if command == "/setup":
            details.append("  Confirm : SAVE stores configuration first, then runs read-only /info verification")
        details.append("")
    return details


def _compact_help_lines() -> list[str]:
    return [
        "DESCRIPTION",
        "  User-local M32 Bridge installer and verifier.",
        "USAGE",
        "  sh scripts/install.sh [OPTIONS]",
        r"  .\scripts\install.ps1 [OPTIONS]",
        "OPTIONS",
        "  -h/--help --dry-run --json --platform <name>",
        "  --version <vX.Y.Z> --channel <stable|prerelease|main>",
        "  --ref <FULL_40_HEX_SHA> --local",
        "INSTALL SELECTION",
        "  Standalone: latest stable | Checkout: local",
        "  main and commit installs require explicit selection.",
        "STATUS COLOURS",
        "  Green OK | Yellow Action | Red Error | Slate Info/not checked",
        "COMMANDS",
        "  /help /health /setup /get-info /verify-device /doctor-runtime /mcp-config",
        "  /status /contact /clear /exit",
        "CONFIGURATION",
        "  Saved config is authoritative; no local IP guessing or discovery.",
        "SAFETY",
        "  No shell execution, scan, OSC writes, /set, admin, or system Python changes.",
        "SHELL",
        "  /health -> m32-bridge health",
        "  /setup -> m32-bridge setup",
        "  /get-info -> m32-bridge get-info",
        "  /verify-device -> m32-bridge detect-device",
        "  /doctor-runtime -> m32-bridge doctor-runtime",
        "FIELD GUIDE",
        "  Console IP     Known address only; setup will not guess or scan",
        "  Port           Default 10023",
        "  Save           SAVE stores configuration first, then verifies with /info",
        "NAVIGATION",
        "  / commands | Up/Down | Enter/Tab | ESC | PageUp/Down in help",
        "CONTACT",
        f"  {CONTACT_URL}",
        f"  {CONTACT_EMAIL}",
        f"  {CONTACT_PHONE}",
    ]


def _split_columns(left: list[str], right: list[str], width: int, colors: Colors | None = None) -> list[str]:
    colors = colors or Colors(False)
    gap = "   |   "
    left_width = max((width - len(gap)) // 2, 40)
    right_width = max(width - left_width - len(gap), 20)
    left = _fit_plain_lines(left, left_width)
    right = _fit_plain_lines(right, right_width)
    rows: list[str] = []
    for index in range(max(len(left), len(right))):
        left_text = left[index] if index < len(left) else ""
        right_text = right[index] if index < len(right) else ""
        left_cell = _pad_plain_cell(left_text[:left_width], left_width, colors)
        right_cell = _pad_plain_cell(right_text[:right_width], right_width, colors)
        rows.append(f"{left_cell}{colors.BORDER}{gap}{colors.RESET_BG}{right_cell}")
    return rows


def _fit_plain_lines(lines: list[str], width: int) -> list[str]:
    fitted: list[str] = []
    for line in lines:
        if not line:
            fitted.append("")
            continue
        indent = len(line) - len(line.lstrip())
        subsequent = " " * min(indent, max(width - 1, 0))
        fitted.extend(
            textwrap.wrap(
                line,
                width=max(width, 1),
                subsequent_indent=subsequent,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    return fitted


def _pad_plain_cell(text: str, width: int, colors: Colors) -> str:
    return f"{_style_help_line(text, colors)}{' ' * max(width - len(text), 0)}"


def _style_help_line(line: str, colors: Colors) -> str:
    if not line:
        return ""
    stripped = line.strip()
    if stripped in HELP_SECTIONS:
        return f"{colors.PRIMARY}{colors.BOLD}{line}{colors.RESET_BG}"
    if stripped and set(stripped) <= {"-", "="}:
        return f"{colors.BORDER}{line}{colors.RESET_BG}"
    if stripped.startswith("/") or "m32-bridge" in stripped or "scripts/install" in stripped:
        return f"{colors.PRIMARY}{line}{colors.RESET_BG}"
    if stripped.startswith("Green"):
        return f"{colors.SUCCESS}{line}{colors.RESET_BG}"
    if stripped.startswith("Yellow"):
        return f"{colors.ACCENT}{line}{colors.RESET_BG}"
    if stripped.startswith("Red"):
        return f"{colors.ERROR}{line}{colors.RESET_BG}"
    if stripped.startswith("Slate") or stripped.startswith(("POSIX", "PowerShell", "Console IP", "Port", "Save", "Label", "Intended target", "Saved config", "Shell alias")):
        return f"{colors.MUTED}{line}{colors.RESET_BG}"
    return f"{colors.TEXT}{line}{colors.RESET_BG}"


def derive_dns_status(statuses: Iterable[str]) -> str:
    relevant = [status for status in statuses if status]
    checked = [status for status in relevant if status != "not_checked"]
    if not checked:
        return "not_checked"
    if any(status in {"reachable", "http_error", "tls_error"} for status in checked):
        return "resolved"
    if any(status == "dns_error" for status in checked):
        return "dns_error"
    return "not_determined"


def _bounded_url_status(url: str, timeout: float) -> str:
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": INSTALLER_SOURCE_USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return "reachable" if 200 <= getattr(response, "status", 200) < 400 else "http_error"
    except urllib.error.HTTPError:
        return "http_error"
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return "dns_error"
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "timeout"
        if isinstance(reason, ssl.SSLError):
            return "tls_error"
        return "unreachable"
    except (TimeoutError, socket.timeout):
        return "timeout"
    except ssl.SSLError:
        return "tls_error"


def render_command_picker(query: str = "/", *, color: bool = False) -> str:
    return SlashCommandPicker(SLASH_COMMANDS).render(query, Colors(color))


def render_runtime_command_picker(query: str = "/", *, color: bool = False) -> str:
    return SlashCommandPicker(RUNTIME_SLASH_COMMANDS).render(query, Colors(color))


def read_single_keypress() -> str:
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                return "UP"
            if ch2 == b"P":
                return "DOWN"
            if ch2 == b"I":
                return "PAGEUP"
            if ch2 == b"Q":
                return "PAGEDOWN"
            return "SPECIAL"
        if ch == b"\r":
            return "ENTER"
        if ch == b"\t":
            return "TAB"
        if ch == b"\x1b":
            return "ESC"
        return ch.decode("utf-8", errors="ignore")
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1).decode("utf-8", errors="ignore")
        if ch == "\x1b":
            ready, _, _ = select.select([fd], [], [], 0.15)
            if ready and os.read(fd, 1).decode("utf-8", errors="ignore") in ("[", "O"):
                ready2, _, _ = select.select([fd], [], [], 0.15)
                if ready2:
                    ch3 = os.read(fd, 1).decode("utf-8", errors="ignore")
                    if ch3 in {"5", "6"}:
                        ready3, _, _ = select.select([fd], [], [], 0.15)
                        if ready3:
                            os.read(fd, 1)
                        return "PAGEUP" if ch3 == "5" else "PAGEDOWN"
                    return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(ch3, "SPECIAL")
            return "ESC"
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == "\t":
            return "TAB"
        if ch in ("\x7f", "\x08"):
            return "BACKSPACE"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class TTYSession:
    def __init__(self, *, stream: TextIO | None = None, color: bool = True, fullscreen: bool = True):
        self.stream = stream or sys.stdout
        self.color = color
        self.fullscreen = fullscreen

    def __enter__(self) -> "TTYSession":
        if self.color and self.fullscreen:
            enable_windows_ansi(stream=self.stream)
            self.stream.write(disable_autowrap())
            self.stream.write(hide_cursor())
            self.stream.write(clear_screen_with_background(color=True))
            self.stream.flush()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if self.color and self.fullscreen:
            self.stream.write(reset_terminal())
            self.stream.flush()
        return False

    def draw(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()


def _m32_bridge_module_path() -> Path:
    import m32_bridge

    return Path(str(m32_bridge.__file__)).resolve()


def verify_runtime_import_provenance(environ: dict[str, str] | None = None) -> dict[str, Any]:
    environment = dict(os.environ if environ is None else environ)
    import mcp
    import pydantic
    import yaml

    module_path = _m32_bridge_module_path()
    if any(part.startswith("m32-bridge-bootstrap-") for part in module_path.parts):
        raise RuntimeError("Installed runtime resolved m32_bridge from bootstrap source.")
    installed_marker = environment.get("M32_BRIDGE_INSTALLED_RUNTIME") == "1"
    app_value = environment.get("M32_BRIDGE_APP_DIR")
    if installed_marker:
        if not app_value:
            raise RuntimeError("Installed runtime marker is missing the application directory.")
        app_path = Path(app_value).expanduser().resolve()
        try:
            module_path.relative_to(app_path / "src")
        except ValueError:
            raise RuntimeError("Installed runtime did not import m32_bridge from the installed application.") from None
    return {
        "m32_bridge_path": str(module_path),
        "yaml_available": bool(yaml.__file__),
        "mcp_available": bool(mcp.__file__),
        "pydantic_available": bool(pydantic.__file__),
        "installed_runtime": installed_marker,
        "bootstrap_source": False,
    }


def run_runtime_tty() -> int:
    try:
        provenance = verify_runtime_import_provenance()
    except Exception:
        print("Runtime Console could not verify the installed application. Run m32-bridge health.", file=sys.stderr)
        return 1
    from m32_bridge.installer.runtime_manager import local_runtime_diagnostics, platform_information

    precondition = evaluate_console_precondition()
    app_path = Path(os.environ.get("M32_BRIDGE_APP_DIR") or _m32_bridge_module_path().parents[2])
    default_launcher = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "M32Bridge" / "bin" / "m32-bridge.cmd"
        if os.name == "nt"
        else Path.home() / ".local" / "bin" / "m32-bridge"
    )
    launcher_path = Path(os.environ.get("M32_BRIDGE_LAUNCHER") or default_launcher)
    runtime_environ = dict(os.environ)
    installed_uv = runtime_environ.get("M32_BRIDGE_UV_BIN")
    if installed_uv:
        runtime_environ["PATH"] = str(Path(installed_uv).parent) + os.pathsep + runtime_environ.get("PATH", "")
    runtime = local_runtime_diagnostics(
        environ=runtime_environ,
        app_path=str(app_path),
        launcher_path=str(launcher_path),
    )
    runtime["import_provenance"] = provenance
    result = {
        "tty_mode": "runtime",
        "ok": True,
        "status": "ready",
        "app_path": str(app_path),
        "launcher_path": str(launcher_path),
        "runtime_info": runtime,
        "platform_info": platform_information(environ=runtime_environ),
        "console_configured": precondition.configured,
        "console_precondition_state": precondition.state,
        "console_connection_status": "not_checked",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "dry_run": False,
    }
    build_runtime_status(result, environ=runtime_environ, refresh=False)
    surface = "windows" if os.name == "nt" else "posix"
    final, _ = run_tty_app(surface, result, dry_run=False, color=True)
    return int(final.get("runtime_exit_code", 0 if final.get("ok") else 1))


def run_tty_app(
    surface: str,
    result: dict[str, Any],
    *,
    dry_run: bool,
    color: bool = True,
    key_reader: Any | None = None,
    line_input: Any | None = None,
    stream: TextIO | None = None,
    size_provider: Any | None = None,
) -> tuple[dict[str, Any], str]:
    stream = stream or sys.stdout
    if result.get("tty_mode") == "runtime" and not isinstance(result.get("runtime_status_snapshot"), dict):
        build_runtime_status(result, refresh=False)
    picker_commands = RUNTIME_SLASH_COMMANDS if result.get("tty_mode") == "runtime" else SLASH_COMMANDS
    picker = SlashCommandPicker(picker_commands)
    input_buffer = ""
    panel_lines: list[str] | None = None
    panel_offset = 0
    view = "main"
    setup_state: SetupState | None = None
    pending_setup_command: str | None = None
    key_reader = key_reader or read_single_keypress
    transcript: list[str] = []

    def draw() -> None:
        nonlocal panel_offset
        width, height = terminal_size(size_provider)
        if panel_lines:
            panel_offset = _next_panel_offset(panel_offset, len(panel_lines), height, "CLAMP")
        frame = render_full_screen(
            surface,
            result,
            dry_run=dry_run,
            color=color,
            width=width,
            height=height,
            panel_lines=panel_lines,
            panel_offset=panel_offset,
            input_buffer=input_buffer,
            picker=picker,
            view=view,
        )
        transcript.append(frame)
        stream.write(frame)
        stream.flush()

    def gate_runtime_command(command: str) -> bool:
        nonlocal pending_setup_command, panel_lines, panel_offset, input_buffer, view
        if result.get("tty_mode") != "runtime" or not _requires_console_config(command):
            return False
        precondition = evaluate_console_precondition()
        _store_console_precondition(result, precondition)
        if precondition.state == "ready":
            return False
        pending_setup_command = None
        if precondition.state == "setup_required":
            eligible = _can_retry_after_setup(command)
            if eligible:
                pending_setup_command = command
            panel_lines = render_setup_required_panel(
                command,
                allow_setup_chain=eligible,
                color=color,
            ).splitlines()
        else:
            panel_lines = render_runtime_command_failure("CONFIG_INVALID", log_path=None, color=color).splitlines()
        panel_offset = 0
        input_buffer = ""
        view = "action"
        return True

    def start_setup_flow() -> None:
        nonlocal setup_state, pending_setup_command, panel_lines, panel_offset, input_buffer, view
        try:
            setup_state = _setup_state_from_current_config()
        except Exception:
            setup_state = None
            pending_setup_command = None
            panel_lines = render_runtime_command_failure("CONFIG_INVALID", log_path=None, color=color).splitlines()
            panel_offset = 0
            input_buffer = ""
            view = "action"
            return
        panel_lines = _setup_state_lines(setup_state, color=color)
        panel_offset = 0
        input_buffer = ""
        view = "setup"

    with TTYSession(stream=stream, color=color, fullscreen=True):
        draw()
        while True:
            try:
                key = key_reader()
            except (EOFError, OSError, RuntimeError):
                output = "Input stream is unavailable. Reopen the Runtime Console in an interactive terminal."
                if result.get("tty_mode") == "runtime":
                    result.update(
                        ok=False,
                        status="runtime_input_failed",
                        runtime_exit_reason="input_failure",
                        runtime_exit_code=1,
                    )
                panel_lines = output.splitlines()
                panel_offset = 0
                view = "panel"
                draw()
                break
            except KeyboardInterrupt:
                if result.get("tty_mode") == "runtime":
                    result.update(ok=False, status="interrupted", runtime_exit_reason="interrupted", runtime_exit_code=130)
                else:
                    result["status"] = "cancelled"
                    result["ok"] = False
                break

            if key == "ESC":
                if setup_state is not None:
                    setup_state = None
                    pending_setup_command = None
                    panel_lines = None
                    panel_offset = 0
                    input_buffer = ""
                    view = "main"
                    draw()
                    continue
                if input_buffer.startswith("/"):
                    input_buffer = ""
                    panel_lines = None
                    panel_offset = 0
                    view = "main"
                    draw()
                    continue
                if panel_lines is not None:
                    pending_setup_command = None
                    panel_lines = None
                    panel_offset = 0
                    view = "main"
                    draw()
                    continue
                if result.get("tty_mode") == "runtime":
                    result.update(runtime_exit_reason="user_exit", runtime_exit_code=0, ok=True)
                break
            if key == "BACKSPACE":
                if setup_state is not None:
                    if SETUP_FIELDS[setup_state.field_index][0] == "target_type":
                        panel_lines = _setup_state_lines(setup_state, color=color)
                        draw()
                        continue
                    setup_state.current_text = setup_state.current_text[:-1]
                    panel_lines = _setup_state_lines(setup_state, color=color)
                    draw()
                    continue
                input_buffer = input_buffer[:-1]
                if not input_buffer:
                    view = "main"
                draw()
                continue
            if key in {"PAGEUP", "PAGEDOWN"} and panel_lines:
                _, height = terminal_size(size_provider)
                panel_offset = _next_panel_offset(panel_offset, len(panel_lines), height, key)
                draw()
                continue
            if key in {"UP", "DOWN"} and setup_state is not None and SETUP_FIELDS[setup_state.field_index][0] == "target_type":
                _move_setup_target_selector(setup_state, key)
                panel_lines = _setup_state_lines(setup_state, color=color)
                panel_offset = 0
                view = "setup"
                draw()
                continue
            if key in {"UP", "DOWN"} and panel_lines and not input_buffer.startswith("/"):
                _, height = terminal_size(size_provider)
                panel_offset = _next_panel_offset(panel_offset, len(panel_lines), height, key)
                draw()
                continue
            if key in {"UP", "DOWN"} and input_buffer.startswith("/"):
                picker.move(input_buffer, key)
                draw()
                continue
            if key in {"TAB", "ENTER"}:
                if setup_state is not None and key == "ENTER":
                    output, done = _advance_setup_state(setup_state, result, color=color)
                    if done:
                        setup_state = None
                        post_setup_precondition = evaluate_console_precondition()
                        _store_console_precondition(result, post_setup_precondition)
                        if pending_setup_command and _retry_is_ready(pending_setup_command, post_setup_precondition):
                            retry_command = pending_setup_command
                            pending_setup_command = None
                            width, _ = terminal_size(size_provider)
                            retry_output, stop = execute_installer_command(retry_command, result, color=color, width=width)
                            panel_lines = retry_output.splitlines() if retry_output else None
                            if stop:
                                draw()
                                break
                        else:
                            pending_setup_command = None
                            panel_lines = output.splitlines() if output else None
                        panel_offset = 0
                        view = "action"
                    elif output:
                        panel_lines = [output, "", *_setup_state_lines(setup_state, color=color)]
                        panel_offset = 0
                        view = "setup"
                    else:
                        panel_lines = _setup_state_lines(setup_state, color=color)
                        panel_offset = 0
                        view = "setup"
                    draw()
                    continue
                if key == "ENTER" and pending_setup_command and setup_state is None:
                    start_setup_flow()
                    draw()
                    continue
                if input_buffer.startswith("/"):
                    selected = picker.select(input_buffer) or input_buffer
                    if selected == "/setup":
                        if result.get("tty_mode") == "runtime":
                            execute_installer_command(selected, result, color=color, width=terminal_size(size_provider)[0])
                        start_setup_flow()
                        draw()
                        continue
                    if gate_runtime_command(selected):
                        draw()
                        continue
                    width, _ = terminal_size(size_provider)
                    output, stop = execute_installer_command(selected, result, color=color, width=width)
                    if selected in {"/clear", "clear"}:
                        panel_lines = None
                        panel_offset = 0
                        view = "main"
                    else:
                        panel_lines = output.splitlines() if output else None
                        panel_offset = 0
                        view = _view_for_command(selected)
                    input_buffer = ""
                    draw()
                    if stop:
                        if result.get("tty_mode") == "runtime":
                            result.update(runtime_exit_reason="user_exit", runtime_exit_code=0, ok=True)
                        break
                    continue
                if key == "ENTER":
                    command = input_buffer
                    parser = parse_runtime_command if result.get("tty_mode") == "runtime" else parse_installer_command
                    parsed_command = parser(command)
                    if parsed_command == "/setup":
                        if result.get("tty_mode") == "runtime":
                            execute_installer_command(parsed_command, result, color=color, width=terminal_size(size_provider)[0])
                        start_setup_flow()
                        draw()
                        continue
                    if parsed_command and gate_runtime_command(parsed_command):
                        draw()
                        continue
                    width, _ = terminal_size(size_provider)
                    output, stop = execute_installer_command(command, result, color=color, width=width)
                    panel_lines = output.splitlines() if output else None
                    panel_offset = 0
                    view = _view_for_command(parsed_command or command)
                    input_buffer = ""
                    draw()
                    if stop:
                        if result.get("tty_mode") == "runtime":
                            result.update(runtime_exit_reason="user_exit", runtime_exit_code=0, ok=True)
                        break
                    continue
            if len(str(key)) == 1 and ord(str(key)) >= 32:
                if setup_state is not None:
                    if SETUP_FIELDS[setup_state.field_index][0] == "target_type":
                        if _select_setup_target_numeric(setup_state, str(key)):
                            panel_lines = _setup_state_lines(setup_state, color=color)
                            panel_offset = 0
                            view = "setup"
                            draw()
                        continue
                    setup_state.current_text += str(key)
                    panel_lines = _setup_state_lines(setup_state, color=color)
                    view = "setup"
                    draw()
                    continue
                input_buffer += str(key)
                if input_buffer == "/":
                    picker.index = 0
                    view = "picker"
                draw()
    return result, "".join(transcript)


def _runtime_has_console_config() -> bool:
    return evaluate_console_precondition().state == "ready"


def _requires_console_config(command: str) -> bool:
    metadata = RUNTIME_COMMAND_REGISTRY.get(command)
    return bool(metadata and metadata.requires_console_config)


def _can_retry_after_setup(command: str) -> bool:
    metadata = RUNTIME_COMMAND_REGISTRY.get(command)
    return bool(
        metadata
        and metadata.requires_console_config
        and metadata.read_only
        and metadata.safe_to_retry_after_setup
    )


def _retry_is_ready(command: str, precondition: Any | None = None) -> bool:
    state = precondition.state if precondition is not None else evaluate_console_precondition().state
    return _can_retry_after_setup(command) and state == "ready"


def _requires_console_setup(command: str) -> bool:
    return _requires_console_config(command) and evaluate_console_precondition().state == "setup_required"


def _store_console_precondition(result: dict[str, Any], precondition: Any) -> None:
    result["console_precondition_state"] = precondition.state
    result["console_configured"] = precondition.state == "ready"
    result["configuration_state"] = {
        "setup_required": "missing",
        "config_invalid": "invalid",
        "ready": "valid",
    }[precondition.state]
    connection = str(result.get("console_connection_status") or "not_checked")
    result["operational_state"] = (
        "setup_required"
        if precondition.state == "setup_required"
        else "config_invalid"
        if precondition.state == "config_invalid"
        else "console_connected"
        if connection == "reachable"
        else "console_unreachable"
        if connection == "unreachable"
        else "console_not_checked"
    )


def termios_error() -> tuple[type[BaseException], ...]:
    try:
        import termios

        return (termios.error,)
    except Exception:
        return ()


def handle_tty_command(command: str, result: dict[str, Any], *, color: bool = False) -> tuple[str, bool]:
    return execute_installer_command(command, result, color=color)


def wrap_stdout_for_tty(stream: TextIO | None = None) -> TextIO:
    stream = stream or sys.stdout
    return CRLFStdout(stream) if is_tty(stdout=stream) else stream


def terminal_reset_sequence(*, color: bool = True) -> str:
    return reset_terminal() if color else ""


def _render_header(colors: Colors, *, tty_mode: str = "installer") -> str:
    return "\n".join(_header_lines(colors, width=80, tty_mode=tty_mode))


def _header_lines(colors: Colors, *, width: int, tty_mode: str = "installer") -> list[str]:
    border = "=" * max(min(width - 2, 76), 8)
    if tty_mode == "runtime":
        logo_lines = [RUNTIME_BANNER, RUNTIME_SUBTITLE, POWERED_BY]
    elif width <= 100:
        logo_lines = [BANNER, POWERED_BY]
    else:
        logo_lines = [BANNER, POWERED_BY, *DXBMARK_ASCII_LOGO.splitlines()]
    return [
        f"{colors.BORDER}+{border}+{colors.RESET_BG}",
        *[f" {colors.PRIMARY}{colors.BOLD}{line}{colors.RESET_BG}" for line in logo_lines],
        f"{colors.BORDER}+{border}+{colors.RESET_BG}",
        f" {colors.MUTED}Type {colors.ACCENT}/{colors.MUTED} for interactive menu | Type {colors.ACCENT}/help{colors.MUTED} for list{colors.RESET_BG}",
    ]


def _body_rows(surface: str, result: dict[str, Any], *, dry_run: bool, width: int = 120, height: int = 32) -> list[TTYRow]:
    if result.get("tty_mode") == "runtime":
        return _runtime_body_rows(result, width=width, height=height)
    from m32_bridge.installer.runtime_manager import inspect_runtime, platform_information

    platform_info = result.get("platform_info") or platform_information()
    runtime_info = result.get("runtime_info") or inspect_runtime()
    uv_status = str(result.get("uv_status") or "unknown")
    frozen_execution = "enabled" if result.get("frozen_execution", True) else "not_checked"
    platform_summary = " · ".join(
        str(value)
        for value in (
            f"{platform_info.get('os')} {platform_info.get('version')}".strip(),
            platform_info.get("architecture"),
            platform_info.get("shell"),
        )
        if value
    )
    rows: list[TTYRow] = [
        TTYRow("section", "SYSTEM"),
        TTYRow("field", label="Platform", value=platform_summary, value_style="normal"),
        TTYRow("section", "RUNTIME"),
        TTYRow("field", label="uv", value=f"{uv_status} / {runtime_info.get('uv_version') or 'not_detected'}", value_style="success" if result.get("uv_detected") else "warning"),
        TTYRow("field", label="CPython", value=runtime_info.get("python_version") or "not_detected", value_style="success" if runtime_info.get("managed_python_detected") else "warning"),
        TTYRow("field", label="Frozen execution", value=frozen_execution, value_style="success" if frozen_execution == "enabled" else "warning"),
        TTYRow("field", label="System Python", value="unchanged", value_style="success"),
        TTYRow("section", "INSTALLER"),
        TTYRow("field", label="Mode", value="dry-run" if dry_run else "apply", value_style="warning" if dry_run else "success"),
        TTYRow("field", label="State", value=result.get("status"), value_style="success" if result.get("ok") else "warning"),
        TTYRow("field", label="Source", value=result.get("install_source") or "unknown", value_style="normal"),
        TTYRow("section", "SAFETY"),
        TTYRow("field", label="Administrator", value="not_used", value_style="success"),
        TTYRow("field", label="OSC writes", value=result.get("osc_writes_sent", 0), value_style="success"),
        TTYRow("field", label="Network scan", value="not_run", value_style="success"),
        TTYRow("field", label="Hardware verified", value=_bool(result.get("hardware_verified")), value_style="success"),
        TTYRow("text", "Type / to open all commands."),
    ]
    required_actions = result.get("required_actions") or []
    if required_actions:
        rows.extend([TTYRow("blank"), TTYRow("section", "REQUIRED ACTIONS")])
        for action in required_actions:
            rows.append(TTYRow("warning", f"{action.get('action_id')}: {action.get('title')}"))
    return rows


def _runtime_body_rows(result: dict[str, Any], *, width: int = 120, height: int = 32) -> list[TTYRow]:
    snapshot = result.get("runtime_status_snapshot")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("application"), dict):
        snapshot = build_runtime_status(result, refresh=False)
    application = snapshot["application"]
    platform_info = snapshot["platform"]
    runtime = snapshot["python_runtime"]
    source = snapshot["installation_source"]
    config = snapshot["console_configuration"]
    connection = snapshot["console_connection"]
    endpoint = "not_configured" if config["host"] == "not_configured" else f"{config['host']}:{config['port']}"
    app_files = "available" if application["app_path"] != "not_available" and Path(str(application["app_path"])).exists() else "not_found"
    launcher_status = "executable" if application["launcher_path"] != "not_available" and Path(str(application["launcher_path"])).exists() and (os.name == "nt" or os.access(str(application["launcher_path"]), os.X_OK)) else "not_executable"
    if source["release_tag"] != "not_available":
        release_identity = f"Version {application['version']} · Release {source['release_tag']}"
    elif source["source_commit"] != "not_available":
        release_identity = f"Version {application['version']} · Commit {str(source['source_commit'])[:12]}"
    elif source["install_source"] == "local_checkout":
        release_identity = f"Version {application['version']} · Local checkout"
    else:
        release_identity = f"Version {application['version']} · Source unavailable"
    minimal = [
        TTYRow("field", label="Product / version", value=f"{application['product']} · {release_identity}", value_style="normal"),
        TTYRow("field", label="Source / metadata", value=f"{source['source_ref']} · {application['install_metadata_status']}", value_style="normal"),
        TTYRow("field", label="OS / arch", value=f"{platform_info.get('os', 'unknown')} {platform_info.get('version', 'unknown')} · {platform_info.get('architecture', 'unknown')}", value_style="normal"),
        TTYRow("field", label="Managed Python", value=runtime["managed_python_version"], value_style="success"),
        TTYRow("field", label="Configuration state", value=f"{snapshot['configuration_state']} · {endpoint}", value_style=_semantic_style_for_value(snapshot["configuration_state"])),
        TTYRow("field", label="Connection state", value=snapshot["connection_state"], value_style=_semantic_style_for_value(snapshot["connection_state"])),
        TTYRow("field", label="Operational state", value=snapshot["operational_state"], value_style=_semantic_style_for_value(snapshot["operational_state"])),
        TTYRow("field", label="OSC writes", value=0, value_style="success"),
        TTYRow("field", label="Network scan", value="not_run", value_style="success"),
    ]
    if height <= 21:
        return minimal
    compact = [
        TTYRow("section", "APPLICATION"),
        *minimal[:2],
        TTYRow("section", "SYSTEM / RUNTIME"),
        *minimal[2:4],
        TTYRow("section", "CONSOLE"),
        *minimal[4:7],
        TTYRow("section", "SAFETY"),
        *minimal[7:],
    ]
    if height < 30:
        return compact
    return [
        TTYRow("section", "APPLICATION"),
        TTYRow("field", label="Product / version", value=f"{application['product']} · {release_identity}", value_style="normal"),
        TTYRow("field", label="Source ref / install", value=f"{source['source_ref']} · {source['install_source']}", value_style="normal"),
        TTYRow("section", "SYSTEM"),
        TTYRow("field", label="OS / version", value=f"{platform_info.get('os', 'unknown')} {platform_info.get('version', 'unknown')}", value_style="normal"),
        TTYRow("field", label="Architecture / shell", value=f"{platform_info.get('architecture', 'unknown')} · {platform_info.get('shell', 'unknown')}", value_style="normal"),
        TTYRow("section", "RUNTIME"),
        TTYRow("field", label="uv", value=f"{runtime['uv_version']} · {runtime['uv_path']}", value_style="success" if runtime["uv_detected"] else "warning"),
        TTYRow("field", label="Managed CPython", value=runtime["managed_python_version"], value_style="success"),
        TTYRow("field", label="Frozen launcher", value=runtime["frozen_launcher"], value_style="success"),
        TTYRow("field", label="Application files", value=f"{app_files} · {application['app_path']}", value_style=_semantic_style_for_value(app_files)),
        TTYRow("field", label="Launcher status", value=f"{launcher_status} · {application['launcher_path']}", value_style=_semantic_style_for_value(launcher_status)),
        TTYRow("section", "CONSOLE"),
        TTYRow("field", label="Configuration state", value=snapshot["configuration_state"], value_style=_semantic_style_for_value(snapshot["configuration_state"])),
        TTYRow("field", label="Endpoint", value=endpoint, value_style="normal"),
        TTYRow("field", label="Label / intended target", value=f"{config['label']} · {display_target_type(config['intended_target'])}", value_style="normal"),
        TTYRow("field", label="Connection state", value=snapshot["connection_state"], value_style=_semantic_style_for_value(snapshot["connection_state"])),
        TTYRow("field", label="Operational state", value=snapshot["operational_state"], value_style=_semantic_style_for_value(snapshot["operational_state"])),
        TTYRow("section", "SAFETY"),
        TTYRow("field", label="OSC writes / scan", value="0 · not_run", value_style="success"),
        TTYRow("field", label="Admin / System Python", value="not_used · unchanged", value_style="success"),
        TTYRow("field", label="Hardware verified", value=_bool(snapshot["safety"]["hardware_verified"]), value_style="success"),
        TTYRow("text", "Type / to open all commands."),
    ]


def _body_lines(surface: str, result: dict[str, Any], *, dry_run: bool) -> list[str]:
    colors = Colors(False)
    return [render_semantic_row(row, colors) for row in _body_rows(surface, result, dry_run=dry_run)]


def render_footer_status(
    result: dict[str, Any],
    *,
    color: bool = False,
    view: str = "main",
    width: int = 80,
    panel_footer: str | None = None,
) -> str:
    colors = Colors(color)
    now = datetime.now().strftime("%H:%M:%S")
    state = result.get("status")
    runtime_mode = result.get("tty_mode") == "runtime"
    hints = {
        "picker": "[Up/Down] Navigate | [Tab/Enter] Select | [ESC] Dismiss",
        "help": "[ESC] Back | /status | /contact | /exit",
        "contact": "[ESC] Back | /help | /status | /exit",
        "status": "[ESC] Back | /help | /contact | /exit",
        "panel": "[ESC] Back | /help | /status | /exit",
        "action": "[ESC] Back | /help | /status | /exit",
        "setup": "[Enter] Next field | [Backspace] Edit | [ESC] Cancel setup",
        "mcp": "[ESC] Back | Up/Down/PgUp/PgDn Scroll | /help | /exit",
    }.get(view, "Type / to open all commands. | [ESC] Exit · q/quit/exit · /exit")
    if panel_footer:
        return f"{colors.MUTED}{panel_footer}{colors.RESET_BG}"
    legend = " | Green OK | Yellow Action | Red Error" if width >= 100 else ""
    if runtime_mode:
        application_health = str(result.get("application_health") or "healthy")
        operational_state = str(result.get("operational_state") or "setup_required")
        if application_health != "healthy":
            summary = "RUNTIME ACTION REQUIRED"
            style = colors.ERROR if application_health == "error" else colors.ACCENT
        else:
            summary = {
                "setup_required": "RUNTIME HEALTHY · SETUP REQUIRED",
                "config_invalid": "CONFIG INVALID · RUN /setup",
                "console_not_checked": "RUNTIME HEALTHY · CONSOLE NOT CHECKED",
                "console_unreachable": "RUNTIME HEALTHY · CONSOLE UNREACHABLE",
                "console_connected": "RUNTIME HEALTHY · CONSOLE CONNECTED",
            }.get(operational_state, "RUNTIME HEALTHY · CONSOLE NOT CHECKED")
            style = colors.ERROR if operational_state == "config_invalid" else (colors.ACCENT if operational_state in {"setup_required", "console_unreachable"} else colors.SUCCESS)
        return f"{colors.MUTED}{now}{colors.RESET_BG}  {style}{summary}{colors.RESET_BG}  {colors.MUTED}| {hints}{legend}{colors.RESET_BG}"
    uv = "UV OK" if result.get("uv_detected") else "UV SETUP REQUIRED"
    return f"{colors.MUTED}{now}{colors.RESET_BG}  {colors.SUCCESS if result.get('ok') else colors.ACCENT}{state}{colors.RESET_BG}  {colors.MUTED}{uv} | {hints}{legend}{colors.RESET_BG}"


def _status_style(status: str) -> str:
    return "success" if status in {"available", "present", "installed_user_local"} else "warning"


def _view_for_command(command: str) -> str:
    normalized = command.strip().lower()
    runtime_spec = RUNTIME_COMMAND_REGISTRY.get(normalized)
    if runtime_spec is not None:
        return runtime_spec.view
    if normalized in {"/help", "help"}:
        return "help"
    if normalized in {"/contact", "contact"}:
        return "contact"
    if normalized in {"/mcp-config", "mcp-config", "m32-bridge mcp-config"}:
        return "mcp"
    if normalized in {"/status", "/status refresh"}:
        return "status"
    if normalized in COMMAND_REGISTRY:
        return "action"
    return "main"


def _source_configuration_state(source_url: str) -> str:
    if "raw.githubusercontent.com/DXBMARK/m32-bridge" in source_url:
        return "configured: github raw installer URL"
    if "github.com/DXBMARK/m32-bridge" in source_url:
        return "configured: github source archive"
    if source_url:
        return "configured: custom source"
    return "not_checked"


def render_config_source_name(source: str | None) -> str:
    return {
        "user_config": "User configuration",
        "environment": "Environment override",
        "env": "Environment override",
        "cli": "Current command",
        "project_config": "Project configuration",
        "project_local_dev_test": "Project configuration",
        "default": "Default value",
        None: "Not configured",
        "": "Not configured",
    }.get(source, str(source))


def display_target_type(value: str | None) -> str:
    return {
        "hardware": "Physical M32 console",
        "emulator": "Emulator / test endpoint",
        "unknown": "Unknown / not declared",
        None: "Unknown / not declared",
        "": "Unknown / not declared",
    }.get(str(value), "Unknown / not declared")


def _target_type_index(value: str | None) -> int:
    canonical = canonical_target_type(value)
    for index, (candidate, _) in enumerate(TARGET_TYPE_OPTIONS):
        if candidate == canonical:
            return index
    return 2


def _target_type_from_index(index: int) -> str:
    index = min(max(index, 0), len(TARGET_TYPE_OPTIONS) - 1)
    return TARGET_TYPE_OPTIONS[index][0]


def _move_setup_target_selector(state: SetupState, direction: str) -> None:
    if direction == "UP":
        state.target_type_index = (state.target_type_index - 1) % len(TARGET_TYPE_OPTIONS)
    elif direction == "DOWN":
        state.target_type_index = (state.target_type_index + 1) % len(TARGET_TYPE_OPTIONS)
    state.values = state.values or {}
    state.values["target_type"] = _target_type_from_index(state.target_type_index)


def _select_setup_target_numeric(state: SetupState, key: str) -> bool:
    if key not in {"1", "2", "3"}:
        return False
    state.target_type_index = int(key) - 1
    state.values = state.values or {}
    state.values["target_type"] = _target_type_from_index(state.target_type_index)
    return True


def canonical_target_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "1": "hardware",
        "physical": "hardware",
        "physical m32": "hardware",
        "physical m32 console": "hardware",
        "hardware": "hardware",
        "2": "emulator",
        "emulator": "emulator",
        "test": "emulator",
        "test endpoint": "emulator",
        "3": "unknown",
        "unknown": "unknown",
        "not declared": "unknown",
        "": "unknown",
    }.get(normalized, "unknown")


def _config_path_text(path: object | None) -> str:
    if not path:
        return "not_configured"
    text = str(path)
    home = str(Path.home())
    return text.replace(home, "~", 1) if text.startswith(home) else text


def _resolved_runtime_metadata() -> Any:
    from m32_bridge.config.runtime import resolve_runtime_config

    return resolve_runtime_config(cli_args={}, environ=dict(os.environ), allow_project_local=False)


def _setup_state_from_current_config() -> SetupState:
    from m32_bridge.config.runtime import default_user_config_path

    resolution = _resolved_runtime_metadata()
    configuration_unreadable = resolution.error_code == "CONFIG_INVALID"
    current_values: dict[str, str] = {}
    if not configuration_unreadable and resolution.effective_host:
        current_values["host"] = str(resolution.effective_host)
    if not configuration_unreadable and resolution.effective_port:
        current_values["port"] = str(resolution.effective_port)
    if not configuration_unreadable and resolution.effective_label:
        current_values["label"] = str(resolution.effective_label)
    current_values["target_type"] = "unknown" if configuration_unreadable else (resolution.effective_intended_target_type or "unknown")
    return SetupState(
        current_values=current_values,
        source_by_field={} if configuration_unreadable else dict(resolution.source_by_field),
        config_path=_config_path_text(resolution.config_path or default_user_config_path()),
        target_type_index=_target_type_index("unknown" if configuration_unreadable else resolution.effective_intended_target_type),
        configuration_unreadable=configuration_unreadable,
    )


def _repository_url_from_source(source_url: str) -> str:
    parsed = urllib.parse.urlparse(source_url)
    if parsed.netloc in {"github.com", "www.github.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return f"https://github.com/{parts[0]}/{parts[1]}"
    if parsed.netloc == "raw.githubusercontent.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return f"https://github.com/{parts[0]}/{parts[1]}"
    return "not_configured" if not source_url else "custom_source"


def _panel_visible_capacity(height: int) -> int:
    return max(height - 11, 3)


def _next_panel_offset(current: int, total_lines: int, height: int, key: str) -> int:
    visible_capacity = _panel_visible_capacity(height)
    max_offset = max(total_lines - visible_capacity, 0)
    if key == "UP":
        return max(current - 1, 0)
    if key == "DOWN":
        return min(current + 1, max_offset)
    if key == "PAGEUP":
        return max(current - visible_capacity, 0)
    if key == "PAGEDOWN":
        return min(current + visible_capacity, max_offset)
    return min(current, max_offset)


def _source_refresh_urls_for_result(result: dict[str, Any]) -> tuple[str, str] | None:
    """Return one exact official installer/archive pair or disable refresh.

    Installer status must never invent a moving ``main`` source when the current
    plan has no validated immutable or versioned source identity.
    """

    from m32_bridge.installer.install_metadata import (
        OFFICIAL_REPOSITORY_URL,
        build_official_release_urls,
        normalize_source_commit,
        validate_release_tag,
    )

    install_source = str(result.get("install_source") or "")
    if install_source in {"", "local_checkout", "custom"}:
        return None
    platform_text = str(result.get("platform") or "").lower()
    surface = "windows" if platform_text.startswith("windows") else "posix"
    release_tag = result.get("release_tag")
    provided_archive = str(result.get("source_archive_url") or result.get("source_url") or "")
    provided_installer = str(result.get("installer_asset_url") or result.get("raw_installer_url") or "")

    if release_tag not in {None, ""}:
        try:
            tag = validate_release_tag(release_tag)
        except ValueError:
            return None
        archive_name = "m32-bridge-source.zip" if surface == "windows" else "m32-bridge-source.tar.gz"
        installer_name = "install.ps1" if surface == "windows" else "install.sh"
        archive_url = f"{OFFICIAL_REPOSITORY_URL}/releases/download/{tag}/{archive_name}"
        installer_url = f"{OFFICIAL_REPOSITORY_URL}/releases/download/{tag}/{installer_name}"
        if provided_archive and provided_archive != archive_url:
            return None
        if provided_installer and provided_installer != installer_url:
            return None
        return installer_url, archive_url

    commit_value = result.get("source_commit") or result.get("source_ref")
    try:
        commit = normalize_source_commit(commit_value)
    except ValueError:
        return None
    urls = build_official_release_urls(surface, commit)
    if provided_archive and provided_archive != urls["source_archive_url"]:
        return None
    if provided_installer and provided_installer != urls["raw_installer_url"]:
        return None
    return urls["raw_installer_url"], urls["source_archive_url"]


def _detected_shell_name(surface: str) -> str:
    if surface == "windows":
        return "powershell"
    shell = Path(os.environ.get("SHELL", "")).name
    return shell or "unknown"


def _bool(value: Any) -> str:
    return str(bool(value)).lower()
