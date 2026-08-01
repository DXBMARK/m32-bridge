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
from importlib.metadata import PackageNotFoundError, version as package_version
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO
import tomllib


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
POWERED_BY = "Powered by DXBMARK LLC"
CONTACT_URL = "https://www.dxbmark.com"
CONTACT_EMAIL = "support@dxbmark.com"
CONTACT_PHONE = "+971505121583"

DXBMARK_ASCII_LOGO = r"""
#  ______  ______  __  __    _    ____  _  __
# |  _ \ \/ / __ )|  \/  |  / \  |  _ \| |/ / LLC
# | | | \  /|  _ \| |\/| | / _ \ | |_) | ' /
# | |_| /  \| |_) | |  | |/ ___ \|  _ <| . \
# |____/_/\_\____/|_|  |_/_/   \_\_| \_\_|\_\ dxbmark.com
""".strip("\n")

COMMAND_REGISTRY = {
    "/health": {"desc": "Check runtime and installation readiness", "scope": "local-only", "shell": "m32-bridge health"},
    "/setup": {"desc": "Configure a known console endpoint", "scope": "network read-only; may save config", "shell": "m32-bridge setup"},
    "/get-info": {"desc": "Read information from the configured endpoint", "scope": "network read-only", "shell": "m32-bridge get-info"},
    "/verify-device": {"desc": "Verify the configured endpoint; no network scan", "scope": "network read-only", "shell": "m32-bridge detect-device"},
    "/doctor-runtime": {"desc": "Diagnose local runtime issues", "scope": "local-only", "shell": "m32-bridge doctor-runtime"},
    "/mcp-config": {"desc": "Generate safe MCP client configuration and setup guidance", "scope": "local-only", "shell": "m32-bridge mcp-config"},
    "/status": {"desc": "Show or refresh installer status", "scope": "local; optional bounded source refresh", "shell": "installer-only"},
    "/contact": {"desc": "Show product information, version, publisher and support", "scope": "local-only", "shell": "installer-only"},
    "/help": {"desc": "Show the responsive command guide", "scope": "local-only", "shell": "sh scripts/install.sh --help"},
    "/clear": {"desc": "Clear and redraw the installer screen", "scope": "local-only", "shell": "installer-only"},
    "/exit": {"desc": "Exit and restore the terminal", "scope": "local-only", "shell": "installer-only"},
}
SHELL_ALIASES = {
    "m32-bridge health": "/health",
    "m32-bridge setup": "/setup",
    "m32-bridge get-info": "/get-info",
    "m32-bridge detect-device": "/verify-device",
    "m32-bridge doctor-runtime": "/doctor-runtime",
    "m32-bridge mcp-config": "/mcp-config",
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
PANEL_VIEWS = frozenset({"help", "contact", "status", "panel", "action", "setup", "mcp"})
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


def application_version() -> str:
    try:
        return package_version(PACKAGE_NAME)
    except PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        try:
            metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            value = metadata.get("project", {}).get("version")
            return str(value) if value else "0.1.0-dev"
        except (OSError, tomllib.TOMLDecodeError):
            return "0.1.0-dev"


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
    return "\n".join([_render_header(colors), "", *body, "", footer])


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
    header_raw = _header_lines(colors, width=width)
    max_header = max(1, min(len(header_raw), max(height - 3, 1)))
    header = [pad_ansi_line(line, content_width, color=color) for line in header_raw[:max_header]]
    body_height = max(height - len(header) - 1, 0)
    command_text = f"root/ $ {input_buffer}" if input_buffer else "root/ $ "
    overlay_lines: list[str] = []
    panel_footer: str | None = None
    if input_buffer.startswith("/"):
        command_height_for_picker = 1 if body_height else 0
        picker_available = max(body_height - command_height_for_picker, 1)
        picker_text = _render_picker_overlay(input_buffer, picker or SlashCommandPicker(SLASH_COMMANDS), colors, picker_available)
        overlay_lines = picker_text.splitlines() if picker_text else ["No matching commands"]
        view = "picker"
    elif panel_lines:
        view = view if view != "main" else "panel"
    footer = pad_ansi_line(
        render_footer_status(result, color=color, view=view, width=width),
        content_width,
        color=color,
    )
    main_rows = [render_semantic_row(row, colors) for row in _body_rows(surface, result, dry_run=dry_run)]
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


def _picker_visible_limit(body_height: int) -> int:
    return max(3, min(7, max(body_height - 6, 3), len(SLASH_COMMANDS)))


def _render_picker_overlay(query: str, picker: SlashCommandPicker, colors: Colors, available_rows: int) -> str:
    picker.visible_limit = min(_picker_visible_limit(available_rows + 1), len(picker.filtered(query)) or len(SLASH_COMMANDS))
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
        if row.label in _EQUALS_FIELDS:
            return f"  {colors.MUTED}{row.label}{colors.RESET_BG}{colors.BORDER}={colors.RESET_BG}{_style_value(str(row.value), row.value_style, colors)}"
        return f"  {colors.MUTED}{row.label:<28}{colors.RESET_BG}{colors.BORDER}:{colors.RESET_BG} {_style_value(str(row.value), row.value_style, colors)}"
    if row.kind == "text":
        return f"  {colors.TEXT}{row.text}{colors.RESET_BG}"
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
    from m32_bridge.config.runtime import resolve_runtime_config
    from m32_bridge.installer.runtime_manager import inspect_runtime, platform_information

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
    console = resolve_runtime_config(cli_args={}, environ=dict(os.environ), allow_project_local=False)
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
        _status_field_colored("Configured", _bool(bool(console.effective_host)), "success" if console.effective_host else "muted", colors),
        _status_field_colored("Host", console.effective_host or "not_configured", "normal" if console.effective_host else "muted", colors),
        _status_field_colored("Port", console.effective_port or "not_configured", "normal" if console.effective_host else "muted", colors),
        _status_field_colored("Host source", render_config_source_name(console.source_by_field.get("host")), "muted", colors),
        _status_field_colored("Port source", render_config_source_name(console.source_by_field.get("port")), "muted", colors),
        _status_field_colored("Config file", _config_path_text(console.config_path), "muted", colors),
        _status_field_colored("Label", console.effective_label or "not set", "normal" if console.effective_label else "muted", colors),
        _status_field_colored("Intended target", display_target_type(console.effective_intended_target_type), "normal", colors),
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
        "  --target-version <version>",
        "  JSON mode is machine-readable and never prompts or installs.",
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


def execute_installer_command(
    command: str,
    result: dict[str, Any],
    *,
    color: bool = False,
    input_func: Callable[[str], str] | None = None,
    width: int | None = None,
) -> tuple[str, bool]:
    action = parse_installer_command(command)
    if action is None:
        return "Unknown command. Type / to view allowed commands.", False
    if action in {"", None}:
        return "", False
    if action == "/":
        return render_command_picker("/", color=color), False
    if action == "/help":
        return installer_help_text(color=color, width=width or terminal_size()[0]), False
    if action == "/contact":
        return installer_contact_text(color=color, width=width), False
    if action == "/mcp-config":
        from m32_bridge.installer.mcp_guidance import render_mcp_guidance, render_mcp_guidance_text

        payload = render_mcp_guidance(environ=dict(os.environ), version=application_version())
        return _style_panel_text(render_mcp_guidance_text(payload, width=width or terminal_size()[0]), color=color), False
    if action == "/status":
        return render_status_text(result, color=color), False
    if action == "/status refresh":
        refresh_source_status(result, force=True)
        return render_status_text(result, color=color), False
    if action == "/clear":
        surface = "windows" if str(result.get("platform", "")).startswith("windows") else "posix"
        return render_tty_installer(surface, result, dry_run=bool(result.get("dry_run", True)), color=color), False
    if action == "/exit":
        return "Installer exited. No dependency or console write action was taken.", True
    if action == "/health":
        from m32_bridge.cli import health

        payload = health()
        payload.update(
            {
                "runtime": _local_runtime_payload(result),
                "osc_writes_sent": 0,
                "network_scan": False,
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
    source_url = str(result.get("source_url") or "")
    github_url = "https://github.com/"
    raw_url = _raw_installer_url_for_result(result)
    archive_url = _source_archive_url_for_result(result)
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
                "attempted_path": None,
                "intended_path": "/info",
                "probe_not_run": True,
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
    payload["scan_attempted"] = False
    payload["osc_writes_sent"] = 0
    result["console_connection_status"] = "reachable" if payload.get("connected") else "unreachable"
    return render_setup_result_panel(payload, color=color)


def _execute_console_read(action: str, result: dict[str, Any], *, color: bool = False) -> str:
    from m32_bridge.cli import detect_device_runtime, get_info_runtime
    from m32_bridge.config.runtime import resolve_runtime_config

    resolution = resolve_runtime_config(cli_args={}, environ=dict(os.environ), allow_project_local=False)
    if not resolution.effective_host:
        return "Run /setup first. No configured endpoint is available."
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
    payload["osc_writes_sent"] = 0
    payload["hardware_verified"] = bool(payload.get("hardware_verified") is True and payload.get("classification") == "HARDWARE_VERIFIED")
    payload["production_live_ready"] = False
    result["console_connection_status"] = "reachable" if payload.get("connected") else "unreachable"
    if action == "/get-info":
        return render_get_info_panel(payload, color=color)
    return render_verify_device_panel(payload, color=color)


def _local_runtime_payload(result: dict[str, Any]) -> dict[str, Any]:
    from m32_bridge.installer.runtime_manager import local_runtime_diagnostics

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
        "Existing configuration found" if current_values.get("host") else "No existing console endpoint is configured.",
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
            rendered = _human_value(value)
            if len(rendered) > 70 and "/" in rendered:
                lines.append(f"  {colors.MUTED}{label:<26}{colors.RESET_BG}:")
                lines.append(f"    {_style_value(rendered, style, colors)}")
            else:
                lines.append(_status_field_colored(label, rendered, style, colors))
    if notes:
        lines.extend(["", _section_title("RESULT", colors), _separator("-" * 60, colors)])
        lines.extend(f"  {_style_value(note, _semantic_style_for_value(note), colors)}" for note in notes)
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


def render_doctor_runtime_panel(payload: dict[str, Any], *, color: bool = False) -> str:
    status_text = str(payload.get("status", "")).lower()
    healthy = bool(
        payload.get("healthy") is True
        or payload.get("ok") is True
        or status_text in {"ok", "healthy", "ready", "passed"}
    )
    return _panel(
        "DOCTOR RUNTIME",
        [
            (
                "RUNTIME",
                [
                    ("uv", "detected" if payload.get("uv_detected") else "not_detected", "success" if payload.get("uv_detected") else "muted"),
                    ("uv version", _value_or(payload, "uv_version", "not_detected"), "normal"),
                    ("uv path", _value_or(payload, "uv_path", "not_detected"), "muted"),
                    ("CPython version", _value_or(payload, "python_version", "not_detected"), "normal"),
                    ("Python path", _value_or(payload, "python_path", "not_detected"), "muted"),
                    ("Managed runtime", "ready" if payload.get("managed_python_detected") else "action required", "success" if payload.get("managed_python_detected") else "warning"),
                ],
            ),
            (
                "INSTALLATION",
                [
                    ("App files", _value_or(payload, "app_files", _value_or(payload, "app_path_status")), _semantic_style_for_value(_value_or(payload, "app_files", _value_or(payload, "app_path_status")))),
                    ("Launcher file", _value_or(payload, "launcher_file", _value_or(payload, "launcher_path_status")), _semantic_style_for_value(_value_or(payload, "launcher_file", _value_or(payload, "launcher_path_status")))),
                    ("Launcher executable", _value_or(payload, "launcher_executable"), _semantic_style_for_value(_value_or(payload, "launcher_executable"))),
                    ("PATH visibility", _value_or(payload, "path_visibility"), _semantic_style_for_value(_value_or(payload, "path_visibility"))),
                ],
            ),
            (
                "POLICY",
                [
                    ("Current user only", "true", "success"),
                    ("Administrator required", "false", "success"),
                    ("System Python modified", "false", "success"),
                    ("Global Python installed", "false", "success"),
                    ("Default aliases installed", "false", "success"),
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
                    ("Latency", payload.get("latency_ms") or payload.get("latency") or "not_available", "normal"),
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
                    ("Network scan", "not run", "success"),
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
    intended = payload.get("intended_target_type") or "unknown"
    return _panel(
        "DEVICE VERIFICATION",
        [
            (
                "CONFIGURED INTENT",
                [
                    ("Intended target", display_target_type(intended), "normal"),
                    ("Source", render_config_source_name(sources.get("intended_target_type") or sources.get("host")), "muted"),
                ],
            ),
            (
                "OBSERVED CONNECTION",
                [
                    ("Configured endpoint", payload.get("endpoint") or f"{payload.get('configured_host') or payload.get('host', 'configured')}:{payload.get('configured_port') or payload.get('port', 10023)}", "normal"),
                    ("Connected", _bool(connected), "success" if connected else "warning"),
                    ("Observed target", payload.get("observed_target_type") or "unknown", "normal" if connected else "muted"),
                    ("Classification", payload.get("classification") or "unknown", "normal"),
                ],
            ),
            (
                "VERIFICATION",
                [
                    ("Hardware verified", _bool(hardware_verified), "success"),
                    ("Production ready", "false", "success"),
                ],
            ),
            (
                "SAFETY",
                [
                    ("OSC writes", payload.get("osc_writes_sent", 0), "success"),
                    ("Network scan", "not run", "success"),
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
    return _panel(
        "SETUP RESULT",
        [
            (
                "CONFIGURATION",
                config_rows,
            ),
            (
                "CONNECTION VERIFICATION",
                [
                    ("Attempted path", payload.get("attempted_path") if payload.get("attempted_path") else "not_attempted", "normal"),
                    ("Intended path", payload.get("intended_path") or "/info", "normal"),
                    ("Connected", _bool(connected), "success" if connected else "warning"),
                    ("Endpoint verified", _bool(endpoint_verified), "success" if endpoint_verified else "warning"),
                    ("Response", "received" if connected else payload.get("verification_status") or payload.get("status") or "not_run", "normal"),
                    ("Classification", payload.get("classification") or "not_observed", "normal" if connected else "muted"),
                    ("Probe not run", _bool(payload.get("probe_not_run", False)), "success"),
                ],
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
    return f"  {label:<26}: {_human_value(value)}"


def _status_field_colored(label: str, value: Any, style: str, colors: Colors) -> str:
    rendered = _human_value(value)
    return f"  {colors.MUTED}{label:<26}{colors.RESET_BG}: {_style_value(rendered, style, colors)}"


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
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "M32-Bridge-Installer/0.1"})
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
    picker = SlashCommandPicker(SLASH_COMMANDS)
    input_buffer = ""
    panel_lines: list[str] | None = None
    panel_offset = 0
    view = "main"
    setup_state: SetupState | None = None
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

    with TTYSession(stream=stream, color=color, fullscreen=True):
        draw()
        while True:
            try:
                key = key_reader()
            except (EOFError, OSError, RuntimeError):
                output = "Input stream is unavailable. Press ESC to exit or reopen the installer in an interactive terminal."
                stop = True
                panel_lines = output.splitlines()
                panel_offset = 0
                view = "panel"
                draw()
                if stop:
                    break
                continue
            except KeyboardInterrupt:
                result["status"] = "cancelled"
                result["ok"] = False
                break

            if key == "ESC":
                if setup_state is not None:
                    setup_state = None
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
                    panel_lines = None
                    panel_offset = 0
                    view = "main"
                    draw()
                    continue
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
                if input_buffer.startswith("/"):
                    selected = picker.select(input_buffer) or input_buffer
                    if selected == "/setup":
                        setup_state = _setup_state_from_current_config()
                        panel_lines = _setup_state_lines(setup_state, color=color)
                        panel_offset = 0
                        view = "setup"
                        input_buffer = ""
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
                        break
                    continue
                if key == "ENTER":
                    command = input_buffer
                    if parse_installer_command(command) == "/setup":
                        setup_state = _setup_state_from_current_config()
                        panel_lines = _setup_state_lines(setup_state, color=color)
                        panel_offset = 0
                        view = "setup"
                        input_buffer = ""
                        draw()
                        continue
                    width, _ = terminal_size(size_provider)
                    output, stop = execute_installer_command(command, result, color=color, width=width)
                    panel_lines = output.splitlines() if output else None
                    panel_offset = 0
                    view = "panel"
                    input_buffer = ""
                    draw()
                    if stop:
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


def _render_header(colors: Colors) -> str:
    return "\n".join(_header_lines(colors, width=80))


def _header_lines(colors: Colors, *, width: int) -> list[str]:
    border = "=" * max(min(width - 2, 76), 8)
    if width <= 100:
        logo_lines = [BANNER, POWERED_BY]
    else:
        logo_lines = [BANNER, POWERED_BY, *DXBMARK_ASCII_LOGO.splitlines()]
    return [
        f"{colors.BORDER}+{border}+{colors.RESET_BG}",
        *[f" {colors.PRIMARY}{colors.BOLD}{line}{colors.RESET_BG}" for line in logo_lines],
        f"{colors.BORDER}+{border}+{colors.RESET_BG}",
        f" {colors.MUTED}Type {colors.ACCENT}/{colors.MUTED} for interactive menu | Type {colors.ACCENT}/help{colors.MUTED} for list{colors.RESET_BG}",
    ]


def _body_rows(surface: str, result: dict[str, Any], *, dry_run: bool) -> list[TTYRow]:
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
    uv = "UV OK" if result.get("uv_detected") else "UV SETUP REQUIRED"
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
    return f"{colors.MUTED}{now}{colors.RESET_BG}  {colors.SUCCESS if result.get('ok') else colors.ACCENT}{state}{colors.RESET_BG}  {colors.MUTED}{uv} | {hints}{legend}{colors.RESET_BG}"


def _status_style(status: str) -> str:
    return "success" if status in {"available", "present", "installed_user_local"} else "warning"


def _view_for_command(command: str) -> str:
    normalized = command.strip().lower()
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
    resolution = _resolved_runtime_metadata()
    current_values: dict[str, str] = {}
    if resolution.effective_host:
        current_values["host"] = str(resolution.effective_host)
    if resolution.effective_port:
        current_values["port"] = str(resolution.effective_port)
    if resolution.effective_label:
        current_values["label"] = str(resolution.effective_label)
    current_values["target_type"] = resolution.effective_intended_target_type or "unknown"
    return SetupState(
        current_values=current_values,
        source_by_field=dict(resolution.source_by_field),
        config_path=_config_path_text(resolution.config_path),
        target_type_index=_target_type_index(resolution.effective_intended_target_type),
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


def _raw_installer_url_for_result(result: dict[str, Any]) -> str:
    from m32_bridge.installer.runtime_manager import OFFICIAL_RAW_INSTALLER_URLS

    platform_text = str(result.get("platform") or "").lower()
    surface = "windows" if platform_text.startswith("windows") else "posix"
    source_url = str(result.get("source_url") or "")
    if "raw.githubusercontent.com" in source_url:
        return source_url
    return OFFICIAL_RAW_INSTALLER_URLS[surface]


def _source_archive_url_for_result(result: dict[str, Any]) -> str:
    from m32_bridge.installer.runtime_manager import OFFICIAL_SOURCE_ARCHIVE_URLS

    platform_text = str(result.get("platform") or "").lower()
    surface = "windows" if platform_text.startswith("windows") else "posix"
    source_url = str(result.get("source_url") or "")
    if "github.com" in source_url and "archive" in source_url:
        return source_url
    return OFFICIAL_SOURCE_ARCHIVE_URLS[surface]


def _detected_shell_name(surface: str) -> str:
    if surface == "windows":
        return "powershell"
    shell = Path(os.environ.get("SHELL", "")).name
    return shell or "unknown"


def _bool(value: Any) -> str:
    return str(bool(value)).lower()
