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
BANNER = "DXBMARK M32 BRIDGE INSTALLER"
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
    "/status": {"desc": "Show or refresh installer status", "scope": "local; optional bounded source refresh", "shell": "installer-only"},
    "/contact": {"desc": "Show DXBMARK contact details", "scope": "local-only", "shell": "installer-only"},
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
}
_PICKER_ORDER = (
    "/help",
    "/contact",
    "/status",
    "/clear",
    "/exit",
    "/health",
    "/setup",
    "/get-info",
    "/verify-device",
    "/doctor-runtime",
)
SLASH_COMMANDS = [
    {
        "cmd": command,
        "desc": COMMAND_REGISTRY[command]["desc"],
        "category": "Action" if command in {"/health", "/setup", "/get-info", "/verify-device", "/doctor-runtime"} else "Utility",
    }
    for command in _PICKER_ORDER
]
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

    def __post_init__(self) -> None:
        if self.values is None:
            self.values = {}


SETUP_FIELDS = (
    ("host", "Known console host", "required; no guessing or scan"),
    ("port", "Port", "10023"),
    ("label", "Label", "optional"),
    ("target_type", "Target type", "unknown"),
    ("confirmation", "Type SAVE", "exact SAVE runs read-only /info and saves after success"),
)


@dataclass
class SlashCommandPicker:
    commands: list[dict[str, str]]
    index: int = 0

    def filtered(self, query: str) -> list[dict[str, str]]:
        query = query.lower()
        return [command for command in self.commands if command["cmd"].lower().startswith(query)]

    def move(self, query: str, direction: str) -> None:
        matches = self.filtered(query)
        if not matches:
            self.index = 0
            return
        if direction == "UP":
            self.index = (self.index - 1) % len(matches)
        elif direction == "DOWN":
            self.index = (self.index + 1) % len(matches)

    def select(self, query: str) -> str | None:
        matches = self.filtered(query)
        if not matches:
            return None
        self.index = min(self.index, len(matches) - 1)
        return matches[self.index]["cmd"]

    def render(self, query: str, colors: Colors) -> str:
        matches = self.filtered(query)
        if not matches:
            return ""
        border = "-" * 58
        lines = [f"{colors.BORDER}+-- Available Commands ({len(matches)}) {border[:31]}+{colors.RESET_BG}"]
        for idx, command in enumerate(matches[:7]):
            selected = idx == self.index
            command_text = f"{command['cmd']:<13}"
            desc_text = f"{command['desc']:<42}"
            if selected:
                lines.append(f" {colors.HIGHLIGHT} > {command_text} {desc_text} {colors.RESET_BG}")
            else:
                lines.append(f"   {colors.PRIMARY}{command_text}{colors.RESET_BG} {colors.MUTED}{desc_text}{colors.RESET_BG}")
        lines.append(f"{colors.BORDER}+{border[:58]}+{colors.RESET_BG}")
        lines.append(f" {colors.MUTED}[Up/Down] Navigate | [Tab/Enter] Select | [ESC] Dismiss{colors.RESET_BG}")
        return "\n".join(lines)


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
    if input_buffer.startswith("/"):
        picker_text = (picker or SlashCommandPicker(SLASH_COMMANDS)).render(input_buffer, colors)
        overlay_lines = picker_text.splitlines() if picker_text else ["No matching commands"]
        view = "picker"
    elif panel_lines:
        overlay_lines = [*panel_lines, "", "[ESC] Back"]
        view = view if view != "main" else "panel"
    footer = pad_ansi_line(render_footer_status(result, color=color, view=view, width=width), content_width, color=color)
    main_rows = [render_semantic_row(row, colors) for row in _body_rows(surface, result, dry_run=dry_run)]
    command_height = 1 if body_height else 0
    if overlay_lines and view in {"help", "contact", "status", "panel", "action"}:
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
    if len(main_rows) > main_capacity and main_capacity > 0 and not overlay_lines:
        raw_body[max(main_capacity - 1, 0)] = "More content available"
    body = [pad_ansi_line(line, content_width, color=color) for line in raw_body[:body_height]]
    while len(body) < body_height:
        body.append(pad_ansi_line("", content_width, color=color))
    return header, body, footer


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
        f"{colors.PRIMARY}{colors.BOLD}--- Installer Status ---{colors.RESET_BG}",
        f"installer state: {result.get('status')}",
        f"uv: {'detected' if result.get('uv_detected') else 'missing'} ({result.get('uv_status')})",
        f"install source: {install_source}",
        f"source configuration: {_source_configuration_state(str(result.get('source_url') or ''))}; reachability {source.get('github_repository')}",
        "safety: osc_writes_sent=0, hardware_verified=false, production_live_ready=false",
        "",
        "INSTALLER",
        _status_field("State", result.get("status")),
        _status_field("Mode", mode),
        _status_field("Mode note", mode_note),
        _status_field("User-local", _bool(result.get("user_local", True))),
        _status_field("Administrator required", "false"),
        "",
        "PLATFORM",
        _status_field("OS", platform_info.get("os")),
        _status_field("Version", platform_info.get("version")),
        _status_field("Kernel/build", platform_info.get("kernel_build")),
        _status_field("Architecture", platform_info.get("architecture")),
        _status_field("Shell", platform_info.get("shell")),
        "",
        "RUNTIME",
        _status_field("uv", "detected" if runtime.get("uv_detected") else "not_detected"),
        _status_field("uv version", runtime.get("uv_version") or "not_detected"),
        _status_field("uv path", runtime.get("uv_path") or "not_detected"),
        _status_field("Approved Python", "CPython 3.13.x"),
        _status_field("Managed Python", "detected" if runtime.get("managed_python_detected") else "not_detected"),
        _status_field("Python version", runtime.get("python_version") or "not_detected"),
        _status_field("Python path", runtime.get("python_path") or "not_detected"),
        _status_field("Project range", runtime.get("project_required_range")),
        _status_field("Launcher", runtime.get("launcher")),
        _status_field("PATH visibility", result.get("path_visibility") or result.get("path_updated") or "not_checked"),
        "",
        "Managed Python policy",
        _status_field("Implementation", "CPython"),
        _status_field("Approved version", "3.13.x"),
        _status_field("Project range", ">=3.11,<3.14"),
        _status_field("Installation scope", "current user"),
        _status_field("System Python", "unchanged"),
        "",
        "SOURCE",
        _status_field("Install source", install_source),
        _status_field("Repository", _repository_url_from_source(str(result.get("source_url") or ""))),
        _status_field("Source ref", result.get("source_ref") or "not_configured"),
        _status_field("Local source files", "available" if install_source == "local_checkout" else "not_checked"),
        _status_field("Network HTTPS route", source.get("network_https_route")),
        _status_field("DNS", source.get("dns")),
        _status_field("GitHub repository", source.get("github_repository")),
        _status_field("Raw installer", source.get("raw_installer")),
        _status_field("Source archive", source.get("source_archive")),
        _status_field("Last checked", source.get("last_checked")),
        _status_field("Source note", source_note),
        "",
        "CONSOLE",
        _status_field("Endpoint configured", _bool(bool(console.effective_host))),
        _status_field("Host", console.effective_host or "not_configured"),
        _status_field("Port", console.effective_port or "not_configured"),
        _status_field("Connection status", result.get("console_connection_status") or "not_checked"),
        _status_field("Device verification status", result.get("device_verification_status") or "not_checked"),
        _status_field("Hardware verified", "false"),
        "",
        "SAFETY",
        _status_field("OSC writes sent", 0),
        _status_field("/set", "not_sent"),
        _status_field("Network scan", "not_run"),
        _status_field("Admin elevation", "not_used"),
        _status_field("Production ready", "false"),
    ]
    return "\n".join(rows)


def installer_help_text(*, color: bool = False, width: int = 80) -> str:
    colors = Colors(color)
    left = [
        "DESCRIPTION",
        "  Install, verify and configure M32 Bridge in the current user account.",
        "",
        "USAGE",
        "  POSIX: sh scripts/install.sh [OPTIONS]",
        r"  PowerShell: .\scripts\install.ps1 [OPTIONS]",
        "",
        "SYNTAX NOTES",
        "  [value] optional | <value> required | ... one or more values",
        "",
        "OPTIONS",
        "  -h, --help",
        "  --dry-run",
        "  --json",
        "  --platform <name>",
        "  --target-version <version>",
        "  JSON mode is machine-readable and never prompts or installs.",
        "",
        "STATUS COLOURS",
        "  Green   Available, successful, or safety requirement satisfied",
        "  Yellow  Attention, confirmation, or user action required",
        "  Red     Failure or blocker",
        "  Slate   Information or not checked",
    ]
    right = [
        "INTERACTIVE COMMANDS",
        *_help_command_lines(),
        "",
        "QUICK START",
        "  1. Review System Check.",
        "  2. Resolve yellow Required Actions.",
        "  3. Run /health.",
        "  4. Run /setup with a known console IP.",
        "  5. Run /verify-device.",
        "  6. Run /get-info.",
        "  7. Review /status.",
        "",
        "SAFETY",
        "  No arbitrary shell execution.",
        "  No network scanning.",
        "  No OSC writes. No /set.",
        "  No system Python modification or administrator elevation.",
        "  No IDE/MCP client config writes.",
        "  MCP guidance remains manual-copy local stdio only.",
        "  No production readiness claim without real hardware evidence.",
        "",
        "SETUP FIELDS",
        "  Console IP     Known address only; setup will not guess or scan",
        "  Port           Default 10023",
        "  Save           Only exact SAVE runs /info and saves user-local config after success",
        "",
        "NAVIGATION",
        "  /             Open commands",
        "  Up/Down       Navigate picker",
        "  Enter/Tab     Select",
        "  ESC           Back or exit",
        "  PageUp/Down   Help navigation only if content does not fit",
        "",
        "CONTACT",
        f"  {CONTACT_URL}",
        f"  {CONTACT_EMAIL}",
        f"  {CONTACT_PHONE}",
    ]
    title = f"{colors.PRIMARY}{colors.BOLD}=== Installer Help ==={colors.RESET_BG}"
    if width >= 100:
        content = _split_columns(left, right, width)
        layout = "TWO-COLUMN HELP"
    elif width >= 60:
        content = _fit_plain_lines([*left, "", *right], width)
        layout = "ONE-COLUMN HELP"
    else:
        content = _fit_plain_lines(_compact_help_lines(), width)
        layout = "COMPACT HELP"
    return "\n".join([title, layout, *content])


def installer_contact_text(*, color: bool = False, width: int | None = None) -> str:
    colors = Colors(color)
    terminal_width = width or terminal_size()[0]
    title = "DXBMARK LLC Contact"
    rows = [("Website", CONTACT_URL), ("Email", CONTACT_EMAIL), ("Phone / WhatsApp", CONTACT_PHONE)]
    if terminal_width < 60:
        return "\n".join([title, *[f"{label:<24}: {value}" for label, value in rows]])
    width = min(max(terminal_width - 2, 60), 74)
    label_w = max(len(row[0]) for row in rows)
    lines = [f"{colors.BORDER}+{'-' * (width - 2)}+{colors.RESET_BG}"]
    title_pad = (width - 2 - len(title)) // 2
    lines.append(f"{colors.BORDER}|{colors.RESET_BG}{' ' * title_pad}{colors.TEXT}{title}{colors.RESET_BG}{' ' * (width - 2 - title_pad - len(title))}{colors.BORDER}|{colors.RESET_BG}")
    lines.append(f"{colors.BORDER}+{'-' * (width - 2)}+{colors.RESET_BG}")
    for label, value in rows:
        visible = f" {label:<{label_w}} : {value}"
        pad = max(width - 2 - len(visible), 0)
        lines.append(f"{colors.BORDER}|{colors.RESET_BG} {colors.TEXT}{label:<{label_w}}{colors.RESET_BG} {colors.BORDER}:{colors.RESET_BG} {colors.ACCENT}{value}{colors.RESET_BG}{' ' * pad}{colors.BORDER}|{colors.RESET_BG}")
    lines.append(f"{colors.BORDER}+{'-' * (width - 2)}+{colors.RESET_BG}")
    return "\n".join(lines)


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
        return _action_panel("HEALTH", payload), False
    if action == "/doctor-runtime":
        return _action_panel("DOCTOR RUNTIME", _local_runtime_payload(result)), False
    if action == "/setup":
        if input_func is None:
            return _setup_view_text(), False
        return _execute_setup(input_func, result), False
    if action in {"/get-info", "/verify-device"}:
        return _execute_console_read(action, result), False
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


def _execute_setup(input_func: Callable[[str], str], result: dict[str, Any]) -> str:
    host = input_func("Known console host: ").strip()
    if not host:
        return "Run /setup with a known console IP. No host was guessed and no scan was run."
    port_text = input_func("Port [10023]: ").strip()
    label = input_func("Label [optional]: ").strip() or None
    target_type = input_func("Target type [unknown]: ").strip() or "unknown"
    confirmation = input_func("Type SAVE to run /info and save after success, or CANCEL: ").strip()
    return _execute_setup_payload(
        result,
        host=host,
        port_text=port_text,
        label=label,
        target_type=target_type,
        confirmation=confirmation,
    )


def _execute_setup_payload(
    result: dict[str, Any],
    *,
    host: str,
    port_text: str,
    label: str | None,
    target_type: str,
    confirmation: str,
) -> str:
    try:
        port = int(port_text) if port_text else 10023
    except ValueError:
        return "Invalid port. Enter a value from 1 to 65535."
    if port < 1 or port > 65535:
        return "Invalid port. Enter a value from 1 to 65535."
    if confirmation != "SAVE":
        return _action_panel(
            "SETUP",
            {
                "ok": False,
                "status": "CANCELLED" if confirmation == "CANCEL" else "CONFIRMATION_REQUIRED",
                "message": "Exact SAVE confirmation is required before the read-only /info probe and config save.",
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
        )
    from m32_bridge.cli import setup_runtime

    payload = setup_runtime(
        host=host,
        port=port,
        target_type=target_type,
        label=label,
        save=True,
        confirm_save=True,
    )
    payload["scan_attempted"] = False
    payload["osc_writes_sent"] = 0
    result["console_connection_status"] = "reachable" if payload.get("connected") else "unreachable"
    return _action_panel("SETUP", payload)


def _execute_console_read(action: str, result: dict[str, Any]) -> str:
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
            target_type="unknown",
        )
        title = "VERIFY DEVICE"
        result["device_verification_status"] = payload.get("classification") or payload.get("status")
    payload["scan_attempted"] = False
    payload["osc_writes_sent"] = 0
    payload["hardware_verified"] = bool(payload.get("hardware_verified") is True and payload.get("classification") == "HARDWARE_VERIFIED")
    payload["production_live_ready"] = False
    result["console_connection_status"] = "reachable" if payload.get("connected") else "unreachable"
    return _action_panel(title, payload)


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
            "  Probe/save: only exact SAVE runs read-only /info and saves after success",
            "  CANCEL or any other confirmation performs no network activity",
            "  No guessing. No subnet scan. No OSC writes.",
        ]
    )


def _setup_state_lines(state: SetupState) -> list[str]:
    values = state.values or {}
    current_key, current_label, hint = SETUP_FIELDS[state.field_index]
    lines = [
        "SETUP",
        "  Configure a known console endpoint. No guessing or subnet scan.",
        "  Only exact SAVE runs read-only /info and saves config after success.",
        "  CANCEL or any other value performs no network activity.",
        "",
    ]
    for key, label, default in SETUP_FIELDS:
        marker = ">" if key == current_key else " "
        value = state.current_text if key == current_key else values.get(key, "")
        if not value and default not in {"required; no guessing or scan", "exact SAVE runs read-only /info and saves after success"}:
            value = f"[{default}]"
        lines.append(f"{marker} {label:<20}: {value}")
    lines.extend(["", f"Current field: {current_label} ({hint})", "Enter advances. ESC returns without saving."])
    return lines


def _advance_setup_state(state: SetupState, result: dict[str, Any]) -> tuple[str | None, bool]:
    key = SETUP_FIELDS[state.field_index][0]
    value = state.current_text.strip()
    if key == "host" and not value:
        return "Host is required. No host was guessed and no scan was run.", False
    state.values = state.values or {}
    state.values[key] = value
    state.current_text = ""
    if state.field_index < len(SETUP_FIELDS) - 1:
        state.field_index += 1
        return None, False
    output = _execute_setup_payload(
        result,
        host=state.values.get("host", ""),
        port_text=state.values.get("port", ""),
        label=state.values.get("label") or None,
        target_type=state.values.get("target_type") or "unknown",
        confirmation=state.values.get("confirmation", ""),
    )
    return output, True


def _action_panel(title: str, payload: dict[str, Any]) -> str:
    import json

    return f"{title}\n{json.dumps(payload, indent=2, sort_keys=True, default=str)}"


def _status_field(label: str, value: Any) -> str:
    return f"  {label:<26}: {value}"


def _help_command_lines() -> list[str]:
    lines: list[str] = []
    for command, metadata in COMMAND_REGISTRY.items():
        lines.append(f"  {command:<16} {metadata['desc']}")
        lines.append(f"    Scope: {metadata['scope']}")
        lines.append(f"    Shell: {metadata['shell']}")
    return lines


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
        "INTERACTIVE COMMANDS",
        *_help_command_lines(),
        "QUICK START",
        "  /health -> /setup -> /verify-device -> /get-info -> /status",
        "SAFETY",
        "  No shell execution, scan, OSC writes, /set, admin, or system Python changes.",
        "NAVIGATION",
        "  / commands | Up/Down | Enter/Tab | ESC | PageUp/Down in help",
        "CONTACT",
        f"  {CONTACT_URL}",
        f"  {CONTACT_EMAIL}",
        f"  {CONTACT_PHONE}",
    ]


def _split_columns(left: list[str], right: list[str], width: int) -> list[str]:
    gap = "   |   "
    left_width = max((width - len(gap)) // 2, 40)
    right_width = max(width - left_width - len(gap), 20)
    left = _fit_plain_lines(left, left_width)
    right = _fit_plain_lines(right, right_width)
    rows: list[str] = []
    for index in range(max(len(left), len(right))):
        left_text = left[index] if index < len(left) else ""
        right_text = right[index] if index < len(right) else ""
        rows.append(f"{left_text[:left_width]:<{left_width}}{gap}{right_text[:right_width]}")
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
    width, height = terminal_size(size_provider)
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
        frame = render_full_screen(
            surface,
            result,
            dry_run=dry_run,
            color=color,
            width=width,
            height=height,
            panel_lines=panel_lines[panel_offset:] if panel_lines else None,
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
                    setup_state.current_text = setup_state.current_text[:-1]
                    panel_lines = _setup_state_lines(setup_state)
                    draw()
                    continue
                input_buffer = input_buffer[:-1]
                if not input_buffer:
                    view = "main"
                draw()
                continue
            if key in {"PAGEUP", "PAGEDOWN"} and panel_lines:
                panel_offset = _next_panel_offset(panel_offset, len(panel_lines), height, key)
                draw()
                continue
            if key in {"UP", "DOWN"} and input_buffer.startswith("/"):
                picker.move(input_buffer, key)
                draw()
                continue
            if key in {"TAB", "ENTER"}:
                if setup_state is not None and key == "ENTER":
                    output, done = _advance_setup_state(setup_state, result)
                    if done:
                        setup_state = None
                        panel_lines = output.splitlines() if output else None
                        panel_offset = 0
                        view = "action"
                    elif output:
                        panel_lines = [output, "", *_setup_state_lines(setup_state)]
                        panel_offset = 0
                        view = "setup"
                    else:
                        panel_lines = _setup_state_lines(setup_state)
                        panel_offset = 0
                        view = "setup"
                    draw()
                    continue
                if input_buffer.startswith("/"):
                    selected = picker.select(input_buffer) or input_buffer
                    if selected == "/setup":
                        setup_state = SetupState()
                        panel_lines = _setup_state_lines(setup_state)
                        panel_offset = 0
                        view = "setup"
                        input_buffer = ""
                        draw()
                        continue
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
                        setup_state = SetupState()
                        panel_lines = _setup_state_lines(setup_state)
                        panel_offset = 0
                        view = "setup"
                        input_buffer = ""
                        draw()
                        continue
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
                    setup_state.current_text += str(key)
                    panel_lines = _setup_state_lines(setup_state)
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
    if width < 64:
        logo_lines = [BANNER, "DXBMARK LLC | dxbmark.com"]
    else:
        logo_lines = [BANNER, *DXBMARK_ASCII_LOGO.splitlines()]
    return [
        f"{colors.BORDER}+{border}+{colors.RESET_BG}",
        *[f" {colors.PRIMARY}{colors.BOLD}{line}{colors.RESET_BG}" for line in logo_lines],
        f"{colors.BORDER}+{border}+{colors.RESET_BG}",
        f" {colors.MUTED}Type {colors.ACCENT}/{colors.MUTED} for interactive menu | Type {colors.ACCENT}/help{colors.MUTED} for list{colors.RESET_BG}",
    ]


def _body_rows(surface: str, result: dict[str, Any], *, dry_run: bool) -> list[TTYRow]:
    from m32_bridge.installer.runtime_manager import download_capability, inspect_runtime, platform_information

    required_actions = result.get("required_actions") or []
    source_url = str(result.get("source_url") or "")
    downloads = download_capability(surface=surface)
    platform_info = result.get("platform_info") or platform_information()
    runtime_info = result.get("runtime_info") or inspect_runtime()
    uv_status = str(result.get("uv_status") or "unknown")
    rows: list[TTYRow] = [
        TTYRow("section", "System Check"),
        TTYRow("field", label="OS", value=platform_info.get("os"), value_style="normal"),
        TTYRow("field", label="version", value=platform_info.get("version"), value_style="normal"),
        TTYRow("field", label="kernel/build", value=platform_info.get("kernel_build"), value_style="normal"),
        TTYRow("field", label="architecture", value=platform_info.get("architecture"), value_style="normal"),
        TTYRow("field", label="shell", value=platform_info.get("shell"), value_style="normal"),
        TTYRow("section", "Download capability"),
        TTYRow("field", label="Primary tool", value=downloads["primary_tool"], value_style="success" if "available" in downloads["primary_tool"] else "warning"),
        TTYRow("field", label="wget fallback", value=downloads["wget_fallback"], value_style="muted"),
        TTYRow("field", label="Manual fallback", value=downloads["manual_fallback"], value_style="success"),
        TTYRow("field", label="uv status", value=uv_status, value_style="success" if result.get("uv_detected") else "warning"),
        TTYRow("field", label="uv version", value=runtime_info.get("uv_version") or "not_detected", value_style="muted"),
        TTYRow("field", label="managed Python", value=runtime_info.get("python_version") or "not_detected", value_style="success" if runtime_info.get("managed_python_detected") else "warning"),
        TTYRow("text", "Python strategy: CPython 3.13.x managed by uv; system Python unchanged"),
        TTYRow("blank"),
        TTYRow("section", "Source Check"),
        TTYRow("field", label="install_source", value=result.get("install_source"), value_style="normal"),
        TTYRow("field", label="source_url", value=result.get("source_url"), value_style="muted"),
        TTYRow("field", label="source_ref", value=result.get("source_ref"), value_style="normal"),
        TTYRow("field", label="Source configuration", value=_source_configuration_state(source_url), value_style="muted"),
        TTYRow("field", label="Reachability", value="not_checked", value_style="muted"),
        TTYRow("blank"),
        TTYRow("section", "Install Plan"),
        TTYRow("field", label="mode", value="dry-run" if dry_run else "apply", value_style="warning" if dry_run else "success"),
        TTYRow("field", label="status", value=result.get("status"), value_style="success" if result.get("ok") else "warning"),
        TTYRow("field", label="install_root", value=result.get("install_root"), value_style="muted"),
        TTYRow("field", label="app_path", value=result.get("app_path"), value_style="muted"),
        TTYRow("field", label="launcher_path", value=result.get("launcher_path"), value_style="muted"),
        TTYRow("field", label="user_local", value=_bool(result.get("user_local", True)), value_style="success"),
        TTYRow("field", label="admin_required", value=_bool(result.get("admin_required", False)), value_style="success"),
        TTYRow("blank"),
        TTYRow("section", "Safety"),
        TTYRow("field", label="osc_writes_sent", value=result.get("osc_writes_sent"), value_style="success"),
        TTYRow("field", label="hardware_verified", value=_bool(result.get("hardware_verified")), value_style="success"),
        TTYRow("field", label="production_live_ready", value=_bool(result.get("production_live_ready")), value_style="success"),
        TTYRow("text", "no /set"),
        TTYRow("text", "no OSC writes"),
        TTYRow("text", "no IDE/MCP config writes"),
        TTYRow("blank"),
        TTYRow("section", "Required Actions"),
    ]
    if required_actions:
        for action in required_actions:
            rows.extend(
                [
                    TTYRow("warning", f"{action.get('action_id')}: {action.get('title')}"),
                    TTYRow("field", label="reason", value=action.get("reason"), value_style="warning"),
                    TTYRow("field", label="command", value=action.get("command_preview"), value_style="command"),
                    TTYRow("field", label="confirmation_required", value=_bool(action.get("requires_confirmation")), value_style="warning"),
                ]
            )
    else:
        rows.append(TTYRow("success", "none"))
    rows.extend(
        [
            TTYRow("blank"),
            TTYRow("section", "Quick Actions"),
            TTYRow("command", "/health          Check runtime and installation readiness"),
            TTYRow("command", "/setup           Configure a known console endpoint"),
            TTYRow("command", "/get-info        Read information from the configured endpoint"),
            TTYRow("command", "/verify-device   Verify the configured endpoint; no network scan"),
            TTYRow("command", "/doctor-runtime  Diagnose local runtime issues"),
            TTYRow("text", "Shell equivalents are listed in /help."),
        ]
    )
    return rows


def _body_lines(surface: str, result: dict[str, Any], *, dry_run: bool) -> list[str]:
    colors = Colors(False)
    return [render_semantic_row(row, colors) for row in _body_rows(surface, result, dry_run=dry_run)]


def render_footer_status(result: dict[str, Any], *, color: bool = False, view: str = "main", width: int = 80) -> str:
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
        "setup": "[Enter] Next field | [Backspace] Edit | [ESC] Cancel setup",
    }.get(view, "[/] Commands | [/help] Help | [ESC] Exit")
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
    return max(height - 4, 1)


def _next_panel_offset(current: int, total_lines: int, height: int, key: str) -> int:
    visible_capacity = _panel_visible_capacity(height)
    max_offset = max(total_lines - visible_capacity, 0)
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
