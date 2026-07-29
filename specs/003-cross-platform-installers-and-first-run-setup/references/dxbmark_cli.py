#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DXBMARK Interactive Terminal CLI Tool
======================================
A zero-dependency, cross-platform (macOS, Windows, Linux) Interactive TUI/CLI Application.
Features full custom background styling (#243947), instant slash menu keyboard picker,
and official DXBMARK Flame Orange (#F97E1A) theme integration.

Author: DXBMARK LLC (dxbmark.com)
"""

import os
import sys
import time
import urllib.request
import urllib.error
import json
import threading
from datetime import datetime

# ==========================================
# 1. ENVIRONMENT DETECTION
# ==========================================
IS_TTY = sys.stdin.isatty() and sys.stdout.isatty()

def enable_windows_ansi():
    """Enables VT100 / ANSI escape sequences on Windows Command Prompt/PowerShell."""
    if os.name == 'nt' and IS_TTY:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            mode.value |= 0x0004
            kernel32.SetConsoleMode(handle, mode)
        except Exception:
            os.system('')

enable_windows_ansi()

# ==========================================
# 1b. CRLF-SAFE STDOUT (fixes raw-mode line drift)
# ==========================================
class _CRLFStdout:
    """Wraps sys.stdout so every bare '\\n' also emits '\\r' (i.e. behaves
    like a terminal's ONLCR mode). Plain print() calls only ever emit
    '\\n' - a normal (cooked-mode) terminal auto-translates that to
    '\\r\\n' for you, but tty.setraw() (needed here for arrow-key input)
    disables that translation. Without this wrapper, every line after
    the first in any multi-line print() output starts at whatever column
    the previous line ended on instead of column 1, and drifts further
    right with each successive line - this was the actual root cause of
    printed content (the /contact box, /status, /help, etc.) appearing
    to distort, drift, or vanish entirely off the right edge of the
    terminal after raw mode was enabled. This class only ever translates
    '\\n' that is NOT already preceded by '\\r' in the same write() call,
    so explicit '\\r\\n' sequences elsewhere in the code are untouched."""
    def __init__(self, real):
        self.real = real
    def write(self, s):
        # Replace any '\n' not already preceded by '\r' with '\r\n'.
        # Doing this as a single regex-free pass keeps it fast for the
        # short strings this program writes.
        if '\n' in s:
            out = []
            i = 0
            for ch in s:
                if ch == '\n' and (not out or out[-1] != '\r'):
                    out.append('\r')
                out.append(ch)
            s = ''.join(out)
        return self.real.write(s)
    def flush(self):
        return self.real.flush()
    def isatty(self):
        return self.real.isatty()
    def fileno(self):
        return self.real.fileno()

if IS_TTY:
    sys.stdout = _CRLFStdout(sys.stdout)

# ==========================================
# 2. COLOR & STYLING ENGINE (#243947 & #F97E1A)
# ==========================================
BG_RGB = (36, 57, 71)

class Colors:
    """ANSI 24-bit TrueColor engine mapped for DXBMARK background palette."""
    if IS_TTY:
        RESET = "\x1b[0m"
        BG_DEFAULT = f"\x1b[48;2;{BG_RGB[0]};{BG_RGB[1]};{BG_RGB[2]}m"
        RESET_BG = f"\x1b[0m{BG_DEFAULT}"
        BOLD = "\x1b[1m"
        DIM = "\x1b[2m"
        TEXT = f"\x1b[38;2;240;244;248m{BG_DEFAULT}"
        PRIMARY = f"\x1b[38;2;249;126;26m{BG_DEFAULT}"     # #F97E1A
        SECONDARY = f"\x1b[38;2;255;165;60m{BG_DEFAULT}"
        ACCENT = f"\x1b[38;2;255;210;90m{BG_DEFAULT}"
        MUTED = f"\x1b[38;2;139;162;181m{BG_DEFAULT}"       # Soft slate
        SUCCESS = f"\x1b[38;2;46;204;113m{BG_DEFAULT}"
        BORDER = f"\x1b[38;2;249;126;26m{BG_DEFAULT}"
        HIGHLIGHT = f"\x1b[48;2;249;126;26m\x1b[38;2;20;20;20m\x1b[1m" # Flame Orange BG, near-black text for max readability
    else:
        RESET = ""
        BG_DEFAULT = ""
        RESET_BG = ""
        BOLD = ""
        DIM = ""
        TEXT = ""
        PRIMARY = ""
        SECONDARY = ""
        ACCENT = ""
        MUTED = ""
        SUCCESS = ""
        BORDER = ""
        HIGHLIGHT = ""

DXBMARK_ASCII_LOGO = """
#  ______  ______  __  __    _    ____  _  __
# |  _ \\ \\/ / __ )|  \\/  |  / \\  |  _ \\| |/ / LLC
# | | | \\  /|  _ \\| |\\/| | / _ \\ | |_) | ' /
# | |_| /  \\| |_) | |  | |/ ___ \\|  _ <| . \\
# |____/_/\\_\\____/|_|  |_/_/   \\_\\_| \\_\\_|\\_\\ dxbmark.com
""".strip("\n")

SLASH_COMMANDS = [
    {"cmd": "/services", "desc": "View DXBMARK core engineering services table", "category": "General"},
    {"cmd": "/multiselect", "desc": "Multi-item interactive check selector demo", "category": "UI Toolset"},
    {"cmd": "/spinner", "desc": "Demonstrate animated CLI loading spinners", "category": "UI Toolset"},
    {"cmd": "/status", "desc": "Show system and API infrastructure health", "category": "System"},
    {"cmd": "/contact", "desc": "Display DXBMARK contact details & link", "category": "Company"},
    {"cmd": "/clear", "desc": "Clear terminal output and re-draw banner", "category": "Utility"},
    {"cmd": "/help", "desc": "Show complete command manual & keyboard shortcuts", "category": "Utility"},
    {"cmd": "/exit", "desc": "Exit the interactive terminal session", "category": "Utility"},
]

# ==========================================
# API CONFIGURATION
# ==========================================
# Real endpoint used by /status. Override at runtime with:
#   DXBMARK_API_URL=https://your.endpoint/health python3 dxbmark_cli.py
# Defaults to a public health-check endpoint so the feature is testable
# out of the box without requiring a live DXBMARK backend.
API_STATUS_URL = os.environ.get("DXBMARK_API_URL", "https://www.dxbmark.com")
API_TIMEOUT_SECONDS = 4

# ==========================================
# 3. KEYBOARD INPUT HANDLING
# ==========================================
def get_single_keypress():
    """Reads a single keypress from STDIN (Cross-platform)."""
    if os.name == 'nt':
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            ch2 = msvcrt.getch()
            if ch2 == b'H': return 'UP'
            elif ch2 == b'P': return 'DOWN'
            return 'SPECIAL'
        if ch == b'\r': return 'ENTER'
        if ch == b'\x08': return 'BACKSPACE'
        if ch == b'\t': return 'TAB'
        if ch == b'\x1b': return 'ESC'
        try: return ch.decode('utf-8', errors='ignore')
        except: return ''
    else:
        import tty
        import termios
        import select
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            # IMPORTANT: use os.read(fd, ...) directly, never sys.stdin.read().
            # sys.stdin is a buffered Python TextIOWrapper - a single
            # sys.stdin.read(1) call can silently pull multiple bytes from
            # the OS into Python's internal buffer while only returning one.
            # A subsequent select.select([sys.stdin], ...) then checks the
            # kernel fd (which is now empty) and wrongly reports "no data",
            # even though the rest of the escape sequence ('[', 'A'/'B') is
            # already sitting in Python's buffer. That mismatch is exactly
            # what caused ESC to fire instead of UP/DOWN, and made '[' and
            # 'A'/'B' leak into the input buffer as plain text afterwards.
            # os.read() talks straight to the fd with no hidden buffering,
            # so select() and read() always agree on what's actually pending.
            ch = os.read(fd, 1).decode('utf-8', errors='ignore')
            if ch == '\x1b':
                rlist, _, _ = select.select([fd], [], [], 0.15)
                if rlist:
                    ch2 = os.read(fd, 1).decode('utf-8', errors='ignore')
                    if ch2 in ('[', 'O'):
                        rlist2, _, _ = select.select([fd], [], [], 0.15)
                        if rlist2:
                            ch3 = os.read(fd, 1).decode('utf-8', errors='ignore')
                            if ch3 == 'A': return 'UP'
                            elif ch3 == 'B': return 'DOWN'
                            elif ch3 == 'C': return 'RIGHT'
                            elif ch3 == 'D': return 'LEFT'
                            rlist3, _, _ = select.select([fd], [], [], 0.02)
                            if rlist3:
                                os.read(fd, 1)
                            return 'SPECIAL'
                    # Unrecognized char after ESC (not '[' or 'O') - drop it
                    # rather than treating ESC alone as the key, otherwise
                    # ch2 leaks into the next read as stray text.
                    return 'ESC'
                return 'ESC'
            elif ch in ('\r', '\n'): return 'ENTER'
            elif ch in ('\x7f', '\x08'): return 'BACKSPACE'
            elif ch == '\t': return 'TAB'
            elif ch == '\x03': raise KeyboardInterrupt
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

# ==========================================
# 4. APPLICATION CLASS
# ==========================================
class DXBTerminalApp:
    def __init__(self):
        self.input_buffer = ""
        self.running = True
        self.picker_active = False
        self.picker_index = 0
        self.filtered_commands = []
        self.last_picker_lines = 0
        # Cached connection state for the bottom status bar. Refreshed
        # lazily (not every frame) so the status bar never blocks the
        # keyboard loop on a slow network call.
        self.conn_state = "UNKNOWN"   # ONLINE / OFFLINE / UNKNOWN
        self.conn_last_checked = 0.0
        self.conn_check_interval = 15.0  # seconds between background pings
        self.conn_latency_ms = None
        self._conn_check_in_progress = False
        # Fixed 3-region layout: header (logo, rows 1..header_height),
        # body (scrollable interactive area, rows header_height+1..footer_row-1),
        # footer (status bar, the terminal's very last row). header_height
        # and footer_row are computed once in setup_fixed_layout() and
        # reused everywhere so header/footer never drift or get overwritten
        # by body scrolling.
        self.header_height = 0
        self.footer_row = 0

    def apply_background(self):
        """Fills the entire terminal background with #243947."""
        if IS_TTY:
            sys.stdout.write(f"\x1b[48;2;{BG_RGB[0]};{BG_RGB[1]};{BG_RGB[2]}m\x1b[2J\x1b[H")
            sys.stdout.flush()

    def reset_terminal_theme(self):
        """Restores default system colors on exit without clearing screen."""
        if IS_TTY:
            # Release the scroll region (DECSTBM with no args = full screen)
            # before handing the terminal back, otherwise the user's shell
            # would inherit our restricted scroll area after we exit.
            sys.stdout.write("\x1b[r")
            sys.stdout.write(f"{Colors.RESET}\n")
            sys.stdout.flush()

    def get_terminal_width(self):
        try: return os.get_terminal_size().columns
        except: return 80

    def get_terminal_height(self):
        try:
            h = os.get_terminal_size().lines
            return h if h > 0 else 24
        except Exception:
            return 24

    def clear_screen(self):
        if IS_TTY:
            self.setup_fixed_layout(animated=False)
        else:
            os.system('cls' if os.name == 'nt' else 'clear')

    def _logo_line_count(self):
        # banner box: top border + logo lines + bottom border + hint line + blank line
        return 1 + len(DXBMARK_ASCII_LOGO.split("\n")) + 1 + 1

    def setup_fixed_layout(self, animated=False):
        """Builds the fixed 3-region layout:
          - Header: logo banner, pinned to rows 1..header_height (never
            scrolls, never gets overwritten by body content).
          - Body: rows header_height+1..footer_row-1. A DECSTBM scroll
            region (\x1b[{top};{bottom}r) restricts normal scrolling to
            exactly this band, so any amount of picker/command output
            scrolls only within it - the header above and footer below
            are physically outside the scrolling region and are immune
            to it, which is what fixes the logo getting pushed off, the
            repeated/duplicated picker frames, and the footer disappearing
            that happened when everything shared one unbounded scrollback.
          - Footer: status bar, pinned to the terminal's last row.
        Call this once at startup and again after a terminal resize or
        /clear."""
        height = self.get_terminal_height()
        width = self.get_terminal_width()
        self.header_height = self._logo_line_count()
        self.footer_row = height

        # 1. Clear the whole screen and draw the header at the top.
        sys.stdout.write(f"\x1b[48;2;{BG_RGB[0]};{BG_RGB[1]};{BG_RGB[2]}m\x1b[2J\x1b[H")
        self._draw_header(animated=animated, width=width)

        # 2. Restrict scrolling to the body band only (DECSTBM). Rows are
        # 1-indexed and inclusive; body starts right after the header and
        # ends one row above the footer so the footer row is never part
        # of the scrolling region.
        body_top = self.header_height + 1
        body_bottom = max(self.footer_row - 1, body_top)
        sys.stdout.write(f"\x1b[{body_top};{body_bottom}r")

        # 3. Move cursor into the body and draw the footer once.
        sys.stdout.write(f"\x1b[{body_top};1H")
        sys.stdout.flush()
        self.draw_status_bar()

    def _draw_header(self, animated=False, width=None):
        """Draws the logo banner as the fixed header, rows 1..header_height.
        Never called mid-interaction - only at startup, after /clear, or
        after a detected resize - so it never competes with body redraws."""
        width = width or self.get_terminal_width()
        border_len = min(width - 2, 76)
        border = "═" * border_len

        print(f"{Colors.BORDER}╔{border}╗{Colors.RESET_BG}")
        for line in DXBMARK_ASCII_LOGO.split("\n"):
            if animated and IS_TTY:
                time.sleep(0.03)
            print(f" {Colors.PRIMARY}{Colors.BOLD}{line}{Colors.RESET_BG}")
        print(f"{Colors.BORDER}╚{border}╝{Colors.RESET_BG}")
        print(f" {Colors.MUTED}Type {Colors.ACCENT}/{Colors.MUTED} for interactive menu | Type {Colors.ACCENT}/help{Colors.MUTED} for list{Colors.RESET_BG}")

    def render_banner(self, animated=False):
        """Kept for backward compatibility with any direct callers; now
        just delegates to the fixed-layout setup so the header is always
        drawn through the same pinned-region path."""
        self.setup_fixed_layout(animated=animated)

    def render_status_bar(self):
        """Builds the fixed bottom status bar line: clock | connection | help hint.
        Uses cached connectivity state (non-blocking) refreshed at most
        once per conn_check_interval seconds in the background thread-free
        way: only re-checked here, cheaply, right before drawing."""
        state, latency_ms = self.check_api_connectivity(force=False)
        now_str = datetime.now().strftime("%H:%M:%S")

        if state == "ONLINE":
            conn_str = f"{Colors.SUCCESS}● API ONLINE{f' ({latency_ms}ms)' if latency_ms else ''}{Colors.RESET_BG}"
        elif state == "DEGRADED":
            conn_str = f"{Colors.ACCENT}● API DEGRADED{Colors.RESET_BG}"
        elif state == "OFFLINE":
            conn_str = f"{Colors.SECONDARY}● API OFFLINE{Colors.RESET_BG}"
        else:
            conn_str = f"{Colors.MUTED}● API CHECKING...{Colors.RESET_BG}"

        bar_text = f" {Colors.MUTED}{now_str}{Colors.RESET_BG}  {conn_str}  {Colors.MUTED}[ESC] Help/Dismiss{Colors.RESET_BG}"
        return bar_text

    def render_prompt_and_picker(self, fresh_prompt=False):
        """Renders the prompt line and, if the input starts with '/', a
        dropdown command picker beneath it - then refreshes the fixed
        footer status bar.

        Standard approach, same as any ordinary interactive CLI (bash,
        a Python REPL, etc.): the prompt is written wherever the cursor
        naturally is, using the terminal's own normal scrolling - no
        absolute row tracking, no cross-call bookkeeping. The picker
        overlay below it uses relative cursor movement, but only ever
        within this single function call: it is drawn, then moved back
        up by the exact number of lines it just drew, in the same
        breath. Nothing about that movement depends on where a *previous*
        call left the cursor, so there is nothing left to drift or
        duplicate across keystrokes - which was the root cause of every
        earlier bug in this area."""
        if not IS_TTY:
            return

        if fresh_prompt:
            # Start this prompt on its own fresh line, below whatever was
            # printed before it (startup banner, /clear, or a command's
            # own output) - never erase that output, just move past it.
            sys.stdout.write("\n")

        # Erase this prompt line and anything below it (a previous picker
        # overlay, if this is a mid-typing redraw) using the standard
        # erase-to-end-of-screen sequence - the same technique any
        # ordinary CLI uses. Safe here because the body's DECSTBM scroll
        # region confines it: it can never reach the header above or the
        # footer below, no matter how it's invoked.
        sys.stdout.write("\r\033[J")

        prompt_prefix = f"{Colors.PRIMARY}root/ $ {Colors.TEXT}"
        sys.stdout.write(f"{prompt_prefix}{self.input_buffer}")

        overlay_lines = []

        if self.input_buffer.startswith("/"):
            self.filtered_commands = [c for c in SLASH_COMMANDS if c['cmd'].lower().startswith(self.input_buffer.lower())]

            if self.filtered_commands:
                self.picker_active = True
                if self.picker_index >= len(self.filtered_commands):
                    self.picker_index = 0

                border_str = "─" * 58
                overlay_lines.append(f"{Colors.BORDER}┌── Available Commands ({len(self.filtered_commands)}) {border_str[:32]}┐{Colors.RESET_BG}")

                for idx, cmd_item in enumerate(self.filtered_commands[:7]):
                    is_selected = (idx == self.picker_index)
                    cmd_str = f"{cmd_item['cmd']:<13}"
                    desc_str = f"{cmd_item['desc']:<42}"
                    if is_selected:
                        overlay_lines.append(f" {Colors.HIGHLIGHT} ► {cmd_str} {desc_str} {Colors.RESET_BG}")
                    else:
                        overlay_lines.append(f"   {Colors.PRIMARY}{cmd_str}{Colors.RESET_BG} {Colors.MUTED}{desc_str}{Colors.RESET_BG}")

                overlay_lines.append(f"{Colors.BORDER}└{border_str[:58]}┘{Colors.RESET_BG}")
                overlay_lines.append(f" {Colors.MUTED}[Up/Down] Navigate | [Tab/Enter] Select | [ESC] Dismiss{Colors.RESET_BG}")
            else:
                self.picker_active = False
        else:
            self.picker_active = False

        # Draw the overlay below the prompt, then return to the prompt
        # line - purely relative movement, opened and closed within this
        # one call, so it can never compound across keystrokes.
        if overlay_lines:
            sys.stdout.write("\n" + "\n".join(overlay_lines))
            sys.stdout.write(f"\033[{len(overlay_lines)}A\r\033[{9 + len(self.input_buffer)}C")
            self.last_picker_lines = len(overlay_lines)
        else:
            self.last_picker_lines = 0

        # Fixed bottom status bar - drawn completely independently of the
        # prompt/picker above, pinned to the terminal's actual last row
        # via absolute cursor positioning with save/restore, so it never
        # disturbs where the user is typing.
        self.draw_status_bar()

        sys.stdout.flush()

    def draw_status_bar(self):
        """Draws the status bar pinned to the terminal's last row (the
        fixed footer region), in a cursor save/restore sandwich so it
        never affects the caller's cursor position. Safe to call from
        anywhere: the main loop, execute_command, or any interactive
        sub-screen (multiselect, spinner) - each of those calls this
        after their own redraw so the bar is never left blank.

        Uses \\x1b7 / \\x1b8 (DECSC/DECRC) for save/restore - NOT
        \\x1b[s / \\x1b[u (the SCO/ANSI.SYS save/restore sequences).
        The latter turned out to be unreliable here: it silently failed
        to restore the cursor's row, leaving it stuck at the footer row
        after every call. Since this function is called after nearly
        every render in the program, that one bug was the actual root
        cause behind the vanishing/drifting/duplicated content seen
        throughout earlier debugging - confirmed by reproducing it in
        isolation with a real terminal emulator (pyte) and confirming
        \\x1b7/\\x1b8 fixes it."""
        if not IS_TTY:
            return
        footer_row = self.footer_row or self.get_terminal_height()
        status_bar_text = self.render_status_bar()
        sys.stdout.write("\x1b7")                       # DECSC: save cursor
        sys.stdout.write(f"\x1b[{footer_row};1H")        # jump to footer row, col 1
        sys.stdout.write("\x1b[2K")                     # clear that row
        sys.stdout.write(f"{Colors.BG_DEFAULT}{status_bar_text}{Colors.RESET_BG}")
        sys.stdout.write("\x1b8")                       # DECRC: restore cursor

        sys.stdout.flush()

    def execute_command(self, cmd_input):
        cmd_input = cmd_input.strip()
        if not cmd_input: return

        main_cmd = cmd_input.split()[0].lower()

        print(f"\n{Colors.MUTED}root/ $ {Colors.TEXT}{cmd_input}{Colors.RESET_BG}")

        if main_cmd in ("/exit", "exit", "quit", "q"):
            print(f"\n{Colors.PRIMARY}{Colors.BOLD}Thank you for using DXBMARK Interactive CLI. Goodbye!{Colors.RESET_BG}\n")
            self.running = False
        elif main_cmd in ("/clear", "clear"):
            self.clear_screen()
        elif main_cmd in ("/help", "help", "?"):
            self.show_help()
        elif main_cmd in ("/services", "services"):
            self.show_services()
        elif main_cmd in ("/multiselect", "multiselect"):
            self.demo_multiselect()
        elif main_cmd in ("/spinner", "spinner"):
            self.demo_spinner()
        elif main_cmd in ("/status", "status"):
            self.show_status()
        elif main_cmd in ("/contact", "contact"):
            self.show_contact()
        else:
            print(f"{Colors.SECONDARY}Command not recognized. Type {Colors.PRIMARY}/help{Colors.SECONDARY} for options.{Colors.RESET_BG}")

        self.draw_status_bar()

    def show_services(self):
        print(f"\n{Colors.PRIMARY}{Colors.BOLD}=== DXBMARK LLC Engineering Services ==={Colors.RESET_BG}\n")
        services = [
            ("01", "Cloud Systems Architecture", "ACTIVE"),
            ("02", "AI & LLM Custom Integrations", "ACTIVE"),
            ("03", "Custom CLI & TUI Developer Tools", "ACTIVE"),
            ("04", "Cybersecurity & Code Auditing", "ACTIVE")
        ]
        for id_num, name, status in services:
            print(f" [{Colors.ACCENT}{id_num}{Colors.TEXT}] {name:<32} {Colors.SUCCESS}[{status}]{Colors.RESET_BG}")
        print()

    def demo_multiselect(self):
        print(f"\n{Colors.PRIMARY}{Colors.BOLD}=== DXBMARK Interactive Feature Selector ==={Colors.RESET_BG}")
        options = ["Cloud Monitoring", "Automated Backups", "AI Assistant API", "Zero-Trust Security"]
        selected = [True, False, True, True]

        if not IS_TTY:
            print("Interactive multi-select requires standard TTY terminal.")
            return

        idx = 0
        first_draw = True
        while True:
            if not first_draw:
                # Move back up to the first list line (drawn last
                # iteration) and erase from there down, before redrawing.
                # This relative movement is opened and closed within the
                # loop body itself - it never depends on anything from
                # outside this function, so it cannot drift.
                sys.stdout.write(f"\033[{len(options) + 1}A\r\033[J")
            first_draw = False

            lines = [f" {Colors.TEXT}Select features to deploy (Press Space to toggle, Enter to confirm):{Colors.RESET_BG}"]
            for i, opt in enumerate(options):
                is_selected_row = (i == idx)
                if is_selected_row:
                    # Inside the orange HIGHLIGHT bar, reuse its own text
                    # color for the checkmark instead of Colors.SUCCESS
                    # (green-on-orange read as a clash - see screenshot).
                    mark = "v" if selected[i] else " "
                    lines.append(f"  {Colors.HIGHLIGHT} ► [{mark}] {opt:<25} {Colors.RESET_BG}")
                else:
                    mark = f"{Colors.SUCCESS}v{Colors.TEXT}" if selected[i] else f"{Colors.TEXT} "
                    lines.append(f"    {Colors.TEXT}[{mark}]{Colors.TEXT} {opt:<25}{Colors.RESET_BG}")
            sys.stdout.write("\n".join(lines))
            self.draw_status_bar()
            sys.stdout.flush()

            key = get_single_keypress()
            if key == 'UP': idx = (idx - 1) % len(options)
            elif key == 'DOWN': idx = (idx + 1) % len(options)
            elif key == ' ': selected[idx] = not selected[idx]
            elif key == 'ENTER': break
            elif key == 'ESC': break

        print(f"\n {Colors.SUCCESS}✔ Configured {sum(selected)} active modules.{Colors.RESET_BG}\n")

    def demo_spinner(self):
        if not IS_TTY:
            print("Connecting to cluster...")
            return

        spinners = ["|", "/", "-", "\\"]
        print(f"\n{Colors.PRIMARY}{Colors.BOLD}=== DXBMARK Loading Spinner Demo ==={Colors.RESET_BG}")
        print(f"{Colors.MUTED}This is a UI component demo: an animated CLI progress indicator{Colors.RESET_BG}")
        print(f"{Colors.MUTED}(reusable for any future long-running task in the CLI).{Colors.RESET_BG}\n")
        print(f"{Colors.MUTED}Simulating a connection to DXBMARK cloud infrastructure...{Colors.RESET_BG}")
        for i in range(20):
            sym = spinners[i % len(spinners)]
            sys.stdout.write(f"\r {Colors.PRIMARY}{sym}{Colors.RESET_BG} Loading modules [{i*5 + 5}%]...")
            self.draw_status_bar()
            sys.stdout.flush()
            time.sleep(0.06)
        sys.stdout.write(f"\r {Colors.SUCCESS}✔ Demo complete — spinner animation finished.{Colors.RESET_BG}          \n\n")

    def _perform_real_api_check(self):
        """Actually hits the network. Never called directly from the render
        loop - always either awaited synchronously (force=True, used by
        /status) or run on a background thread (status bar) so a slow or
        dead network never freezes the keyboard loop."""
        req = urllib.request.Request(
            API_STATUS_URL,
            headers={"User-Agent": "DXBMARK-CLI/1.0"}
        )
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
                resp.read(256)  # confirm a real response body, not just a socket
                latency_ms = int((time.time() - start) * 1000)
                self.conn_state = "ONLINE" if resp.status < 400 else "DEGRADED"
                self.conn_latency_ms = latency_ms
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            self.conn_state = "OFFLINE"
            self.conn_latency_ms = None
        finally:
            self.conn_last_checked = time.time()
            self._conn_check_in_progress = False

    def check_api_connectivity(self, force=False):
        """Returns (state, latency_ms_or_None) for the real, live connection
        to API_STATUS_URL - never fabricated.

        force=True  (used by /status): blocks and performs a real synchronous
                     check right now, so the command's printed result is
                     guaranteed accurate at the moment it's shown.
        force=False (used by the status bar every render): never blocks the
                     keyboard loop. If a check is due, it's kicked off on a
                     background thread and the bar shows 'CHECKING...' until
                     that thread updates self.conn_state; otherwise the last
                     real cached result is reused."""
        now = time.time()
        if force:
            self._conn_check_in_progress = True
            self._perform_real_api_check()
            return self.conn_state, self.conn_latency_ms

        due = (now - self.conn_last_checked) >= self.conn_check_interval
        if due and not self._conn_check_in_progress:
            self._conn_check_in_progress = True
            threading.Thread(target=self._perform_real_api_check, daemon=True).start()

        return self.conn_state, self.conn_latency_ms

    def show_status(self):
        print(f"\n{Colors.PRIMARY}{Colors.BOLD}--- DXBMARK System Health ---{Colors.RESET_BG}")
        print(f" {Colors.TEXT}• Terminal Engine :{Colors.RESET_BG} {Colors.SUCCESS}[TUI TrueColor 24-bit Active]{Colors.RESET_BG}")
        print(f" {Colors.TEXT}• Palette Mode    :{Colors.RESET_BG} {Colors.ACCENT}[#243947 Canvas / #F97E1A Flame]{Colors.RESET_BG}")

        print(f" {Colors.MUTED}Pinging {API_STATUS_URL} ...{Colors.RESET_BG}", end="", flush=True)
        state, latency_ms = self.check_api_connectivity(force=True)
        sys.stdout.write("\r\033[K")  # clear the "pinging..." line

        if state == "ONLINE":
            print(f" {Colors.TEXT}• Cloud API       :{Colors.RESET_BG} {Colors.SUCCESS}[ONLINE — {latency_ms}ms]{Colors.RESET_BG}")
        elif state == "DEGRADED":
            print(f" {Colors.TEXT}• Cloud API       :{Colors.RESET_BG} {Colors.ACCENT}[DEGRADED — non-2xx response]{Colors.RESET_BG}")
        else:
            print(f" {Colors.TEXT}• Cloud API       :{Colors.RESET_BG} {Colors.SECONDARY}[OFFLINE — no response]{Colors.RESET_BG}")
        print(f" {Colors.MUTED}Endpoint: {API_STATUS_URL}{Colors.RESET_BG}\n")

    def show_contact(self):
        # Every label and border character below carries an explicit color
        # code. Leaving any segment uncolored lets it fall back to the
        # terminal's default foreground (often near-black), which is what
        # made "Website" and the box labels look unreadable on the dark
        # background - see the reported screenshot.
        width = 53
        title = "DXBMARK LLC Contact"
        rows = [
            ("Website", "https://www.dxbmark.com"),
            ("Support", "support@dxbmark.com"),
            ("WhatsApp", "+971 50 512 1583"),
        ]
        label_w = max(len(r[0]) for r in rows)

        top    = f"{Colors.BORDER}┌{'─' * (width - 2)}┐{Colors.RESET_BG}"
        title_pad = (width - 2 - len(title)) // 2
        title_line = f"{Colors.BORDER}│{Colors.RESET_BG}{Colors.TEXT}{' ' * title_pad}{title}{' ' * (width - 2 - title_pad - len(title))}{Colors.RESET_BG}{Colors.BORDER}│{Colors.RESET_BG}"
        sep    = f"{Colors.BORDER}├{'─' * (width - 2)}┤{Colors.RESET_BG}"
        bottom = f"{Colors.BORDER}└{'─' * (width - 2)}┘{Colors.RESET_BG}"

        print(f"\n{top}")
        print(title_line)
        print(sep)
        for label, value in rows:
            content = f" {Colors.TEXT}{label:<{label_w}}{Colors.RESET_BG} {Colors.BORDER}:{Colors.RESET_BG} {Colors.ACCENT}{value}{Colors.RESET_BG}"
            visible_len = 1 + label_w + 1 + 1 + 1 + len(value)
            pad = max(width - 2 - visible_len, 0)
            print(f"{Colors.BORDER}│{Colors.RESET_BG}{content}{' ' * pad}{Colors.BORDER}│{Colors.RESET_BG}")
        print(f"{bottom}\n")

    def show_help(self):
        print(f"\n{Colors.PRIMARY}{Colors.BOLD}=== Available Commands ==={Colors.RESET_BG}\n")
        for c in SLASH_COMMANDS:
            print(f"  {Colors.PRIMARY}{c['cmd']:<14}{Colors.RESET_BG} {Colors.TEXT}{c['desc']:<45}{Colors.RESET_BG}")
        print()

    def run_fallback(self):
        """Basic input mode for non-TTY web consoles."""
        self.clear_screen()
        self.render_banner(animated=False)
        print(" [!] Running in Basic CLI Mode (Web/IDE Environment Detected)\n")

        while self.running:
            try:
                cmd = input("root/ $ ").strip()
                if cmd:
                    self.execute_command(cmd)
            except (EOFError, KeyboardInterrupt):
                self.running = False

    def run(self):
        if not IS_TTY:
            self.run_fallback()
            return

        self.setup_fixed_layout(animated=True)

        need_fresh_prompt = True
        while self.running:
            self.render_prompt_and_picker(fresh_prompt=need_fresh_prompt)
            need_fresh_prompt = False
            key = get_single_keypress()

            # Handle Navigation inside Slash Command Picker
            if self.picker_active and key in ('UP', 'DOWN'):
                if key == 'UP':
                    self.picker_index = (self.picker_index - 1) % len(self.filtered_commands)
                elif key == 'DOWN':
                    self.picker_index = (self.picker_index + 1) % len(self.filtered_commands)
                continue

            if key == 'ENTER' or key == 'TAB':
                if self.picker_active and self.filtered_commands:
                    self.input_buffer = self.filtered_commands[self.picker_index]['cmd']

                cmd_to_run = self.input_buffer
                self.input_buffer = ""
                self.picker_active = False

                # The last render_prompt_and_picker call left the cursor
                # back at the prompt line (after drawing the picker
                # overlay below it and moving back up). Erase that
                # overlay - it's no longer needed once a command has
                # been chosen - then move to a fresh line before
                # execute_command starts printing its output.
                sys.stdout.write("\r\033[J")
                sys.stdout.write("\n")
                self.execute_command(cmd_to_run)
                need_fresh_prompt = True

            elif key == 'BACKSPACE':
                self.input_buffer = self.input_buffer[:-1]
                self.picker_index = 0

            elif key == 'ESC':
                self.input_buffer = ""
                self.picker_active = False

            elif len(key) == 1 and ord(key) >= 32:
                self.input_buffer += key
                self.picker_index = 0

        # Reset theme cleanly on loop exit
        self.reset_terminal_theme()

def parse_cli_args(app, argv):
    """Maps --flag arguments to slash commands so users can run a command
    directly without entering the interactive picker, e.g.:
        python3 dxbmark_cli.py --services
        python3 dxbmark_cli.py --status
    Returns True if a direct command was handled (caller should not enter
    interactive mode), False otherwise."""
    if len(argv) < 2:
        return False

    flag = argv[1].lstrip("-").lower()
    flag_to_cmd = {
        "services": "/services",
        "status": "/status",
        "contact": "/contact",
        "help": "/help",
        "h": "/help",
        "spinner": "/spinner",
        "multiselect": "/multiselect",
    }

    if flag in ("version", "v"):
        print("DXBMARK Interactive CLI - v1.0")
        return True

    if flag not in flag_to_cmd:
        print(f"Unknown argument: --{flag}")
        print("Available: --services, --status, --contact, --help, --spinner, --multiselect, --version")
        return True

    # Non-interactive runs never need the raw-mode background/banner; just
    # execute the mapped command's output and exit cleanly.
    app.execute_command(flag_to_cmd[flag])
    return True

if __name__ == "__main__":
    app = DXBTerminalApp()
    try:
        if parse_cli_args(app, sys.argv):
            sys.exit(0)
        app.run()
    except KeyboardInterrupt:
        app.reset_terminal_theme()
        print(f"\n{Colors.PRIMARY}{Colors.BOLD}KeyboardInterrupt detected. Exiting DXBMARK CLI...{Colors.RESET}\n")
        sys.exit(0)
