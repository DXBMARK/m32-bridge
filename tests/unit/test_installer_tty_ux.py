from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from m32_bridge.installer.runtime_manager import RuntimeManagerState
from m32_bridge.installer.script_runtime import (
    build_install_result,
    installer_contact_text,
    installer_help_text,
    render_tty_installer,
)
from m32_bridge.installer.tty_app import (
    DXBMARK_ASCII_LOGO,
    CRLFStdout,
    SlashCommandPicker,
    clear_screen_with_background,
    disable_autowrap,
    enable_autowrap,
    enable_windows_ansi,
    handle_tty_command,
    hide_cursor,
    move_cursor,
    pad_ansi_line,
    render_frame,
    render_full_screen,
    render_command_picker,
    reset_terminal,
    run_tty_app,
    show_cursor,
    strip_ansi,
    terminal_size,
    truncate_ansi_safe,
    visible_width,
    TTYSession,
    _next_panel_offset,
)


ROOT = Path(__file__).resolve().parents[2]
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"
REFERENCE_COPY = ROOT / "specs" / "003-cross-platform-installers-and-first-run-setup" / "references" / "dxbmark_cli.py"


def test_json_mode_has_no_banner_or_ansi(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["M32_INSTALL_ASSUME_UV"] = "installed_user_local"
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")

    completed = subprocess.run(
        ["/bin/sh", str(POSIX_INSTALLER), "--dry-run", "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        cwd=ROOT,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert "DXBMARK M32 BRIDGE INSTALLER" not in completed.stdout
    assert "dxbmark.com" not in completed.stdout
    assert "\x1b[" not in completed.stdout


def test_canonical_dxbmark_cli_reference_is_preserved():
    text = REFERENCE_COPY.read_text(encoding="utf-8")

    assert "DXBMARK Interactive Terminal CLI Tool" in text
    assert "#243947" in text
    assert "#F97E1A" in text
    assert "CRLFStdout" in text
    assert "SLASH_COMMANDS" in text


def test_non_tty_plain_mode_does_not_wait_for_input(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["PATH"] = "/usr/bin:/bin"

    completed = subprocess.run(
        ["/bin/sh", str(POSIX_INSTALLER), "--dry-run"],
        check=False,
        input="",
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        cwd=tmp_path,
    )

    assert completed.returncode != 0
    assert "RUNTIME_SETUP_REQUIRED" in completed.stdout
    assert "Installer command" not in completed.stdout
    assert "DXBMARK M32 BRIDGE INSTALLER" not in completed.stdout


def test_tty_renderer_contains_dxbmark_sections_and_safety(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
        install_source="github_release_or_archive",
        source_url="https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz",
        source_ref="main",
    )

    text = render_tty_installer("posix", result, dry_run=True)
    coloured = render_tty_installer("posix", result, dry_run=True, color=True)

    assert "DXBMARK M32 BRIDGE INSTALLER" in text
    assert "dxbmark.com" in text
    assert "Palette:" not in text
    assert "#243947" not in text
    assert "#F97E1A" not in text
    assert "\x1b[48;2;36;57;71m" in coloured
    assert "\x1b[38;2;249;126;26m" in coloured
    assert "Type / for interactive menu | Type /help for list" in text
    for section in ["System Check", "Source Check", "Install Plan", "Safety", "Required Actions", "Quick Actions"]:
        assert section in text
    assert "Python strategy: CPython 3.13.x managed by uv; system Python unchanged" in text
    assert "osc_writes_sent=0" in text
    assert "hardware_verified=false" in text
    assert "production_live_ready=false" in text
    assert "no /set" in text
    assert "/doctor-runtime  Diagnose local runtime issues" in text
    assert "m32-bridge doctor-runtime" not in text
    assert "Shell: m32-bridge doctor-runtime" in installer_help_text()
    assert "[/] Commands" in text


def test_full_background_sequence_ordering_and_final_reset(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    text = render_full_screen("posix", result, dry_run=True, color=True, width=80, height=20)

    assert text.index("\x1b[48;2;36;57;71m") < text.index("\x1b[2J")
    assert text.index("\x1b[2J") < text.index("\x1b[H")
    assert text.index("\x1b[H") < text.index("DXBMARK M32 BRIDGE INSTALLER")
    assert reset_terminal().endswith("\x1b[0m\n")
    assert hide_cursor() == "\x1b[?25l"
    assert show_cursor() == "\x1b[?25h"


def test_full_width_rows_and_footer_positioning(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    header, body, footer = render_frame("posix", result, dry_run=True, color=True, width=80, height=18)

    rows = [*header, *body, footer]
    assert len(rows) == 18
    assert all(visible_width(row) == 79 for row in rows)
    assert all(row.startswith("\x1b[48;2;36;57;71m") for row in rows)
    assert "fresh_install" in strip_ansi(footer)
    assert strip_ansi(body[-1]).startswith("root/ $")


def test_frame_uses_cursor_positioned_rows_without_newline_joining(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    text = render_full_screen("posix", result, dry_run=True, color=True, width=80, height=12)

    assert "\n" not in text
    for row in range(1, 13):
        assert move_cursor(row, 1) in text
    assert text.rfind(move_cursor(12, 1)) < text.rfind("fresh_install")


def test_picker_is_bottom_anchored_and_does_not_push_system_check(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    _, main_body, main_footer = render_frame("posix", result, dry_run=True, color=True, width=80, height=20)
    _, picker_body, picker_footer = render_frame("posix", result, dry_run=True, color=True, width=80, height=20, input_buffer="/")
    main_text_rows = [strip_ansi(row) for row in main_body]
    picker_text_rows = [strip_ansi(row) for row in picker_body]

    assert main_text_rows[0].startswith("System Check")
    assert picker_text_rows[0].startswith("System Check")
    assert any("Available Commands" in row for row in picker_text_rows[-6:])
    assert picker_text_rows[-1].startswith("root/ $ /")
    assert "[/] Commands" in strip_ansi(main_footer)
    assert "[Tab/Enter] Select" in strip_ansi(picker_footer)


def test_small_terminal_uses_compact_header_without_crashing(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    header, body, footer = render_frame("posix", result, dry_run=True, color=True, width=32, height=8)

    assert len([*header, *body, footer]) == 8
    assert all(visible_width(row) == 31 for row in [*header, *body, footer])


def test_ansi_helpers_do_not_cut_sequences_or_miscount_width():
    coloured = "\x1b[38;2;249;126;26mDXBMARK\x1b[48;2;36;57;71m"

    assert strip_ansi(coloured) == "DXBMARK"
    assert visible_width(coloured) == 7
    assert strip_ansi(truncate_ansi_safe(coloured, 3)) == "DXB"
    assert visible_width(pad_ansi_line(coloured, 12, color=True)) == 12
    assert move_cursor(3, 4) == "\x1b[3;4H"
    assert clear_screen_with_background(color=True).startswith("\x1b[48;2;36;57;71m\x1b[2J")
    assert disable_autowrap() == "\x1b[?7l"
    assert enable_autowrap() == "\x1b[?7h"


def test_terminal_size_uses_provider_and_fallback():
    assert terminal_size(lambda: (100, 30)) == (100, 30)


def test_help_pagedown_stops_at_max_offset_not_last_single_line():
    total_lines = 31
    height = 10
    visible_capacity = height - 4
    expected_max_offset = max(total_lines - visible_capacity, 0)

    offset = 0
    for _ in range(20):
        offset = _next_panel_offset(offset, total_lines, height, "PAGEDOWN")

    assert offset == expected_max_offset
    assert offset != total_lines - 1


def test_tty_missing_uv_shows_required_action(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="macos",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
        install_source="github_release_or_archive",
        source_url="https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz",
        source_ref="main",
    )

    text = render_tty_installer("posix", result, dry_run=True)

    assert "INSTALL_UV_USER_LOCAL" in text
    assert "confirmation_required=true" in text
    assert "Install uv in user space" in text
    assert "admin_required=false" in text


def test_installer_help_and_contact_text():
    assert "/help" in installer_help_text()
    assert "/contact" in installer_help_text()
    assert "/status" in installer_help_text()
    assert "JSON mode" in installer_help_text()
    assert "MCP guidance" in installer_help_text()
    assert "https://www.dxbmark.com" in installer_contact_text()
    assert "support@dxbmark.com" in installer_contact_text()


def test_status_command_reports_installer_runtime_source_and_safety(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
        install_source="github_release_or_archive",
        source_url="https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz",
        source_ref="main",
    )

    output, should_stop = handle_tty_command("/status", result)

    assert should_stop is False
    assert "installer state:" in output
    assert "uv: missing" in output
    assert "install source: github_release_or_archive" in output
    assert "source configuration: configured: github source archive" in output
    assert "reachability not_checked" in output.lower() or "reachability" in output.lower()
    assert "osc_writes_sent=0" in output
    assert "hardware_verified=false" in output


def test_command_picker_lists_and_selects_slash_commands():
    picker = SlashCommandPicker(
        [
            {"cmd": "/help", "desc": "help", "category": "Utility"},
            {"cmd": "/status", "desc": "status", "category": "System"},
        ]
    )

    assert picker.select("/") == "/help"
    picker.move("/", "DOWN")
    assert picker.select("/") == "/status"
    rendered = render_command_picker("/")
    assert "/help" in rendered
    assert "[Up/Down] Navigate" in rendered


def test_command_loop_picker_navigation_help_status_clear_and_exit(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    keys = iter(["/", "DOWN", "DOWN", "ENTER", "/", "h", "ENTER", "/", "c", "ENTER", "/", "ESC", "ESC"])

    class Sink:
        def __init__(self):
            self.data = ""

        def write(self, value):
            self.data += value
            return len(value)

        def flush(self):
            return None

    sink = Sink()
    _, transcript = run_tty_app(
        "posix",
        result,
        dry_run=True,
        color=True,
        key_reader=lambda: next(keys),
        stream=sink,
        size_provider=lambda: (80, 18),
    )

    combined = sink.data + transcript
    assert "Available Commands" in combined
    assert "Installer Status" in combined
    assert "Installer Help" in combined
    assert "DXBMARK LLC Contact" in combined
    assert "\x1b[?25h" in combined
    assert "\x1b[r" in combined


def test_command_loop_esc_outside_picker_exits_safely(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    class Sink:
        data = ""

        def write(self, value):
            self.data += value
            return len(value)

        def flush(self):
            return None

    _, transcript = run_tty_app("posix", result, dry_run=True, color=True, key_reader=lambda: "ESC", stream=Sink(), size_provider=lambda: (80, 12))

    assert "DXBMARK M32 BRIDGE INSTALLER" in transcript


def test_command_loop_raw_input_failure_reports_without_prompting(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    class Sink:
        def __init__(self):
            self.data = ""

        def write(self, value):
            self.data += value
            return len(value)

        def flush(self):
            return None

    sink = Sink()
    run_tty_app(
        "posix",
        result,
        dry_run=True,
        color=True,
        key_reader=lambda: (_ for _ in ()).throw(RuntimeError("raw unavailable")),
        line_input=lambda prompt: (_ for _ in ()).throw(AssertionError("line input must not be used in fullscreen")),
        stream=sink,
        size_provider=lambda: (80, 18),
    )

    assert "Input stream is unavailable" in sink.data
    assert "\x1b[?25h" in sink.data


def test_tty_session_restores_terminal_on_exception():
    class Sink:
        def __init__(self):
            self.data = ""

        def write(self, value):
            self.data += value
            return len(value)

        def flush(self):
            return None

    sink = Sink()

    try:
        with TTYSession(stream=sink, color=True):
            sink.write("boom")
            raise RuntimeError("draw failed")
    except RuntimeError:
        pass

    assert "\x1b[?25l" in sink.data
    assert "\x1b[?7l" in sink.data
    assert "\x1b[?7h" in sink.data
    assert "\x1b[?25h" in sink.data
    assert "\x1b[r" in sink.data
    assert sink.data.endswith("\x1b[0m\n")


def test_windows_ansi_enable_is_guarded_on_non_windows():
    if os.name != "nt":
        assert enable_windows_ansi() is False


def test_crlf_stdout_wraps_bare_newlines_only():
    class Sink:
        def __init__(self):
            self.data = ""

        def write(self, value):
            self.data += value
            return len(value)

        def flush(self):
            return None

        def isatty(self):
            return True

        def fileno(self):
            return 1

    sink = Sink()
    wrapped = CRLFStdout(sink)

    wrapped.write("one\ntwo\r\nthree")

    assert sink.data == "one\r\ntwo\r\nthree"


def test_posix_and_powershell_scripts_route_tty_without_admin_or_destructive_commands():
    posix = POSIX_INSTALLER.read_text(encoding="utf-8")
    windows = WINDOWS_INSTALLER.read_text(encoding="utf-8")
    combined = f"{posix}\n{windows}".lower()

    assert "--tty" in posix
    assert "--color" in posix
    assert '$runtimeargs += "--tty"' in windows.lower()
    assert "foregroundcolor" in windows.lower()
    assert "m32_bridge.installer.script_runtime" in combined
    assert DXBMARK_ASCII_LOGO.splitlines()[0].lower() in combined
    assert "48;2;36;57;71" in combined
    assert "38;2;249;126;26" in combined
    assert "palette:" not in combined
    assert "/status" in combined
    assert "/clear" in combined
    assert "/exit" in combined
    assert "dxbmark m32 bridge installer" in combined
    assert "install_uv_user_local" in combined
    assert "sudo" not in combined
    assert "start-process -verb runas" not in combined
    assert "rm -rf" not in combined
    assert "format " not in combined
