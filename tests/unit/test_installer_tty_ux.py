from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

import m32_bridge.cli as cli_module
from m32_bridge.config.runtime import default_user_config_path, resolve_runtime_config
from m32_bridge.installer.application_version import read_project_version
from m32_bridge.installer.runtime_manager import RuntimeManagerState
from m32_bridge.installer.script_runtime import (
    build_install_result,
    installer_contact_text,
    installer_help_text,
    render_tty_installer,
)
from m32_bridge.installer.tty_app import (
    DXBMARK_ASCII_LOGO,
    CONTACT_PHONE,
    BANNER,
    POWERED_BY,
    PACKAGE_NAME,
    PANEL_VIEWS,
    CLI_NAME,
    application_version,
    COMMAND_REGISTRY,
    CRLFStdout,
    Colors,
    SlashCommandPicker,
    SetupState,
    clear_screen_with_background,
    disable_autowrap,
    enable_autowrap,
    enable_windows_ansi,
    handle_tty_command,
    hide_cursor,
    move_cursor,
    pad_ansi_line,
    render_frame,
    render_footer_status,
    render_full_screen,
    render_command_picker,
    render_doctor_runtime_panel,
    render_get_info_panel,
    render_health_panel,
    render_setup_result_panel,
    render_verify_device_panel,
    reset_terminal,
    run_tty_app,
    SLASH_COMMANDS,
    render_config_source_name,
    show_cursor,
    strip_ansi,
    terminal_size,
    truncate_ansi_safe,
    visible_width,
    TTYSession,
    execute_installer_command,
    parse_installer_command,
    _setup_state_from_current_config,
    _view_for_command,
    _next_panel_offset,
    _panel_window,
    _setup_state_lines,
    _advance_setup_state,
    _execute_setup_payload,
    _move_setup_target_selector,
    _select_setup_target_numeric,
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

    assert BANNER in text
    assert POWERED_BY in text
    assert "DXBMARK M32 BRIDGE INSTALLER" not in text
    assert "DXBMARK LLC" in text
    assert "Palette:" not in text
    assert "#243947" not in text
    assert "#F97E1A" not in text
    assert "\x1b[48;2;36;57;71m" in coloured
    assert "\x1b[38;2;249;126;26m" in coloured
    assert "Type / for interactive menu | Type /help for list" in text
    for section in ["SYSTEM", "RUNTIME", "INSTALLER", "SAFETY"]:
        assert section in text
    assert "Type / to open all commands." in text
    assert "Quick Actions" not in text
    assert "Python strategy" not in text
    assert "OSC writes" in text and "0" in text
    assert "Hardware verified" in text and "false" in text
    assert "/doctor-runtime  Diagnose local runtime issues" not in text
    assert "m32-bridge doctor-runtime" not in text
    assert "/doctor-runtime" in installer_help_text()
    assert "Type / to open all commands." in text


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
    assert text.index("\x1b[H") < text.index(BANNER)
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
    assert not strip_ansi(body[-1]).startswith("root/ $")


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

    assert main_text_rows[0].startswith("SYSTEM")
    assert picker_text_rows[0].startswith("SYSTEM")
    assert any("Available Commands" in row for row in picker_text_rows)
    assert any("[Up/Down] Navigate" in row for row in picker_text_rows)
    assert picker_text_rows[-1].startswith("root/ $ /")
    assert "Type / to open all commands." in strip_ansi(main_footer)
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
    visible_capacity = max(height - 11, 3)
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
    assert "Install uv in user space" in text
    assert "Administrator" in text
    assert "not_used" in text


def test_installer_help_and_contact_text():
    help_text = installer_help_text()
    assert "/help" in help_text
    assert "/contact" in help_text
    assert "/status" in help_text
    assert "JSON mode" in help_text
    assert "FIELD GUIDE" in help_text
    assert "q / quit / exit /exit" in help_text
    assert "INSTALL SELECTION" in help_text
    assert "latest stable official Release" in help_text
    assert "--version <vX.Y.Z>" in help_text
    assert "--channel <stable|prerelease|main>" in help_text
    assert "--ref <FULL_40_HEX_SHA>" in help_text
    assert "--local" in help_text
    assert "--target-version" not in help_text
    contact = installer_contact_text()
    assert "X32-BRIDGE MCP" in contact
    assert "Version" in contact
    assert application_version() in contact
    assert PACKAGE_NAME in contact
    assert CLI_NAME in contact
    assert "DXBMARK LLC" in contact
    assert "PURPOSE" in contact
    assert "SAFETY MODEL" in contact
    assert "production" not in contact.lower()
    assert "https://www.dxbmark.com" in contact
    assert "support@dxbmark.com" in contact
    assert CONTACT_PHONE in contact
    assert "End of product information" in contact


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
    assert "INSTALLER STATUS" in output
    assert "INSTALLER" in output
    assert "PLATFORM" in output
    assert "RUNTIME" in output
    assert "SOURCE" in output
    assert "CONSOLE" in output
    assert "SAFETY" in output
    assert "GitHub repository" in output
    assert "Network HTTPS route" in output
    assert "OSC writes sent" in output
    assert "End of status" in output


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
    assert "Showing 1" in rendered
    assert "[Up/Down] Navigate" in rendered


def test_slash_commands_follow_exact_operator_order_and_all_are_selectable():
    expected = [
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
    ]
    assert [item["cmd"] for item in SLASH_COMMANDS] == expected

    picker = SlashCommandPicker(SLASH_COMMANDS)
    selected = []
    for index, command in enumerate(expected):
        selected.append(picker.select("/"))
        assert SlashCommandPicker(SLASH_COMMANDS).select(command) == command
        if index < len(expected) - 1:
            picker.move("/", "DOWN")
    assert selected == expected
    assert expected[expected.index("/doctor-runtime") + 1] == "/mcp-config"
    assert expected[expected.index("/mcp-config") + 1] == "/contact"


def test_command_picker_scrolls_to_all_ten_commands():
    commands = [{"cmd": f"/cmd-{idx}", "desc": f"command {idx}", "category": "Test"} for idx in range(10)]
    picker = SlashCommandPicker(commands)
    picker.visible_limit = 7

    top = picker.render("/", Colors(False))
    assert "Showing 1–7 of 10" in top
    assert "↓ 3 more" in top
    assert "/cmd-0" in top
    assert "/cmd-9" not in top

    for _ in range(9):
        picker.move("/", "DOWN")
    bottom = picker.render("/", Colors(False))
    assert "Showing 4–10 of 10" in bottom
    assert "↑ 3 above" in bottom
    assert "/cmd-9" in bottom

    picker.move("/", "DOWN")
    wrapped = picker.render("/", Colors(False))
    assert "Showing 1–7 of 10" in wrapped
    assert picker.select("/") == "/cmd-0"

    filtered = picker.render("/cmd-9", Colors(False))
    assert "Available Commands (1)" in filtered
    assert "Showing 1–1 of 1" in filtered


def test_picker_last_item_visible_in_final_frame_across_sizes(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    for width, height in [(100, 30), (80, 24), (60, 20), (50, 16)]:
        picker = SlashCommandPicker(SLASH_COMMANDS)
        for _ in range(len(SLASH_COMMANDS) - 1):
            picker.move("/", "DOWN")
        _, body, footer = render_frame(
            "posix",
            result,
            dry_run=True,
            color=False,
            width=width,
            height=height,
            input_buffer="/",
            picker=picker,
        )
        text = "\n".join(strip_ansi(row) for row in body)
        assert "/exit" in text
        assert "Showing" in text
        assert "↑" in text or width <= 50
        assert "> /exit" in text
        assert picker.select("/") == "/exit"
        assert "[Up/Down] Navigate" in text
        assert strip_ansi(body[-1]).startswith("root/ $ /")
        assert len(body) + 1 + len(render_frame("posix", result, dry_run=True, color=False, width=width, height=height, input_buffer="/", picker=picker)[0]) == height
        assert footer


def test_command_loop_picker_navigation_help_status_clear_and_exit(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    keys = iter(["/", "DOWN", "ENTER", "/", "h", "ENTER", "/", "c", "ENTER", "/", "ESC", "ESC"])

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
    assert "INSTALLER STATUS" in combined
    assert "INSTALLER HELP" in combined
    assert "X32-BRIDGE MCP" in combined
    assert "\x1b[?25h" in combined
    assert "\x1b[r" in combined


def test_panel_footer_reports_line_range_and_resize_clamps(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    panel = [f"line {idx}" for idx in range(40)]

    _, _, footer = render_frame(
        "posix",
        result,
        dry_run=True,
        color=False,
        width=80,
        height=12,
        panel_lines=panel,
        panel_offset=0,
        view="status",
    )
    assert "Lines 1" in footer
    assert "of 40" in footer

    _, body, footer = render_frame(
        "posix",
        result,
        dry_run=True,
        color=False,
        width=80,
        height=12,
        panel_lines=panel,
        panel_offset=999,
        view="status",
    )
    assert "of 40" in footer
    assert "End of status" in footer


def test_panel_footer_end_labels_match_view_and_preserve_last_content_line(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    cases = [
        ("help", "help"),
        ("status", "status"),
        ("contact", "contact"),
        ("setup", "setup"),
        ("action", "result"),
        ("panel", "panel"),
    ]

    for view, label in cases:
        final_line = f"{view} final content line"
        panel = [f"{view} line {idx}" for idx in range(40)] + [final_line]
        _, body, footer = render_frame(
            "posix",
            result,
            dry_run=True,
            color=True,
            width=80,
            height=12,
            panel_lines=panel,
            panel_offset=999,
            view=view,
        )
        footer_text = strip_ansi(footer)
        body_text = "\n".join(strip_ansi(row) for row in body)

        assert f"End of {label}" in footer_text
        if view != "panel":
            assert "End of panel" not in footer_text
        assert final_line in body_text
        assert f"End of {label}" not in body_text


def test_semantic_action_panels_do_not_render_raw_json():
    panels = [
        render_health_panel({"ok": True, "runtime": {"uv_detected": True, "managed_python_detected": True, "python_version": "3.13.12"}}),
        render_doctor_runtime_panel({"uv_detected": True, "managed_python_detected": True, "python_version": "3.13.12", "healthy": True}),
        render_get_info_panel({"connected": False, "status": "timeout", "attempted_path": "/info"}),
        render_verify_device_panel({"connected": False, "classification": "unknown", "hardware_verified": False}),
        render_setup_result_panel({"status": "CANCELLED", "attempted_path": "not_attempted", "verification_attempted": False, "config_not_written": True}),
    ]

    for panel in panels:
        first_lines = "\n".join(panel.splitlines()[:3])
        assert "{" not in first_lines
        assert "}" not in first_lines
        assert not panel.lstrip().startswith("{")
        assert '"osc_writes_sent"' not in panel
        assert '"runtime": {' not in panel
    assert "HEALTH" in panels[0]
    assert "DOCTOR RUNTIME" in panels[1]
    assert "CONSOLE INFORMATION" in panels[2]
    assert "DEVICE VERIFICATION" in panels[3]
    assert "SETUP RESULT" in panels[4]
    assert "Read-only verification attempted" in panels[4]


def test_semantic_panels_and_status_have_ansi_when_colored(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    panels = [
        render_health_panel({"ok": True, "runtime": {"uv_detected": True, "managed_python_detected": True, "python_version": "3.13.12"}}, color=True),
        render_doctor_runtime_panel({"status": "ok", "uv_detected": True, "managed_python_detected": True, "launcher_executable": False, "path_visibility": False}, color=True),
        render_get_info_panel({"connected": False, "status": "timeout", "attempted_path": "/info"}, color=True),
        render_verify_device_panel({"connected": False, "classification": "unknown", "hardware_verified": False}, color=True),
        render_setup_result_panel({"status": "CANCELLED", "attempted_path": None, "intended_path": "/info", "probe_not_run": True, "config_not_written": True}, color=True),
        execute_installer_command("/status", result, color=True)[0],
    ]

    for panel in panels:
        assert "\x1b[" in panel
        assert Colors(True).PRIMARY in panel
        assert Colors(True).BOLD in panel
        assert Colors(True).MUTED in panel
    assert Colors(True).SUCCESS in panels[0]
    assert Colors(True).ACCENT in render_setup_result_panel({"saved": False}, color=True)
    assert Colors(True).ERROR in panels[2]


def test_doctor_status_ok_is_healthy_and_preserves_false_values():
    output = render_doctor_runtime_panel(
        {
            "status": "ok",
            "uv_detected": True,
            "managed_python_detected": True,
            "launcher_executable": False,
            "path_visibility": False,
        }
    )

    assert "Healthy" in output
    assert "review action-required fields" not in output
    assert "Launcher executable" in output and ": false" in output
    assert "PATH visibility" in output and ": false" in output
    assert "Launcher executable" in output and "Launcher executable       : not_checked" not in output
    assert "PATH visibility" in output and "PATH visibility           : not_checked" not in output


def test_missing_boolean_values_fall_back_to_not_checked():
    output = render_doctor_runtime_panel({"status": "ok"})

    assert "Launcher executable" in output and ": not_checked" in output
    assert "PATH visibility" in output and ": not_checked" in output


def test_help_title_is_not_duplicated_at_all_widths():
    for width in [120, 100, 80, 50]:
        assert installer_help_text(width=width).count("INSTALLER HELP") == 1


def test_setup_state_colored_styles_are_visible():
    first = _setup_state_lines(SetupState(), color=True)
    first_text = "\n".join(first)
    assert "\x1b[" in first_text
    assert "Step 1/5" in strip_ansi(first_text)
    assert "CONSOLE HOST" in strip_ansi(first_text)
    assert Colors(True).PRIMARY in first_text
    assert Colors(True).MUTED in first_text

    state = SetupState()
    state.values = {"host": "192.0.2.10", "port": "10023", "label": "", "target_type": "unknown"}
    state.field_index = 4
    review_text = "\n".join(_setup_state_lines(state, color=True))
    assert "Step 5/5" in strip_ansi(review_text)
    assert "SAVE" in strip_ansi(review_text)
    assert "CANCEL" in strip_ansi(review_text)
    assert Colors(True).ACCENT in review_text


def test_setup_wizard_step_and_review_lines():
    state = SetupState()
    first = "\n".join(_setup_state_lines(state))
    assert "SETUP CONSOLE" in first
    assert "Step 1/5" in first
    assert "> CONSOLE HOST" in first

    state.values = {"host": "192.0.2.10", "port": "10023", "label": "desk", "target_type": "unknown"}
    state.field_index = 4
    review = "\n".join(_setup_state_lines(state))
    assert "REVIEW SETUP" in review
    assert "Step 5/5" in review
    assert "Send one read-only /info request" in review
    assert "Type SAVE to continue or CANCEL to return" in review


def test_exit_and_utility_aliases_are_safe(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    for command in ["q", "quit", "exit", "/exit"]:
        _, stop = handle_tty_command(command, result)
        assert stop is True

    for command in ["help", "status", "clear", "contact"]:
        _, stop = handle_tty_command(command, result)
        assert stop is False

    for command in ["exit; whoami", "q | tee x", "quit && pwd", "help > file"]:
        output, stop = handle_tty_command(command, result)
        assert stop is False
        assert "Unknown command" in output


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

    assert BANNER in transcript
    assert POWERED_BY in transcript


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
    assert "x32-bridge mcp installer" in combined
    assert "powered by dxbmark llc" in combined
    assert "dxbmark m32 bridge installer" not in combined
    assert "install_uv_user_local" in combined
    assert "sudo" not in combined
    assert "start-process -verb runas" not in combined
    assert "rm -rf" not in combined
    assert "format " not in combined


def test_runtime_config_source_is_visible_and_not_reported_as_discovered(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = home / ".m32-bridge" / "runtime.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "host": "192.168.8.88",
                "port": 10023,
                "label": "Saved Desk",
                "intended_target_type": "unknown",
                "config_scope": "user",
            }
        ),
        encoding="utf-8",
    )
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)

    resolution = resolve_runtime_config(cli_args={}, environ={}, allow_project_local=False)
    output, should_stop = execute_installer_command("/status", result)

    assert should_stop is False
    assert resolution.effective_host == "192.168.8.88"
    assert resolution.source_by_field["host"] == "user_config"
    assert "CONSOLE CONFIGURATION" in output
    assert "192.168.8.88" in output
    assert "User configuration" in output
    assert str(config_path) in output or "~/.m32-bridge/runtime.yaml" in output
    assert "Saved configuration only. This is not device discovery." in output
    assert "detected endpoint" not in output.lower()
    assert "discovered endpoint" not in output.lower()


def test_missing_runtime_config_does_not_adopt_local_or_example_ip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    resolution = resolve_runtime_config(cli_args={}, environ={}, allow_project_local=False)

    assert resolution.effective_host is None
    assert resolution.effective_port is None
    assert resolution.guessed_host is None
    assert resolution.default_scan_attempted is False
    assert "192.168.8.88" not in json.dumps(resolution.__dict__, default=str)


def test_setup_existing_values_loaded_and_enter_preserves_current_values(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "host": "192.168.8.88",
                "port": 10023,
                "label": "FOH",
                "intended_target_type": "hardware",
                "config_scope": "user",
            }
        ),
        encoding="utf-8",
    )
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)

    state = _setup_state_from_current_config()
    first_step = "\n".join(_setup_state_lines(state))
    message, completed = _advance_setup_state(state, result)

    assert state.current_values == {"host": "192.168.8.88", "port": "10023", "label": "FOH", "target_type": "hardware"}
    assert state.source_by_field["host"] == "user_config"
    assert state.config_path in {str(config_path), "~/.m32-bridge/runtime.yaml"}
    assert "Existing configuration found" in first_step
    assert "User configuration" in first_step
    assert "192.168.8.88" in first_step
    assert message is None
    assert completed is False
    assert state.values["host"] == "192.168.8.88"


def test_setup_empty_or_wrong_confirmation_does_not_probe_or_write(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    original = {
        "schema_version": "1",
        "host": "192.168.8.88",
        "port": 10023,
        "label": "Saved",
        "intended_target_type": "unknown",
        "config_scope": "user",
    }
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)

    def forbidden_probe(**_kwargs):
        raise AssertionError("probe must not run without SAVE")

    monkeypatch.setattr(cli_module, "setup_runtime", forbidden_probe)
    for confirmation in ["", "WRONG", "CANCEL"]:
        panel = _execute_setup_payload(
            result,
            host="192.168.8.99",
            port_text="10023",
            label="Candidate",
            target_type="hardware",
            confirmation=confirmation,
        )
        assert "Read-only verification attempted" in panel and "false" in panel
        assert "Config not written" in panel and "true" in panel
        assert "Attempted path" in panel and "not_attempted" in panel
        assert "OSC writes" in panel and "0" in panel
        assert "Network scan" in panel and "not run" in panel
        assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original


def test_setup_save_offline_endpoint_persists_and_reopen_loads_new_values(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "host": "192.168.8.88",
                "port": 10023,
                "intended_target_type": "unknown",
                "config_scope": "user",
            }
        ),
        encoding="utf-8",
    )

    def offline_probe(host, port, **_kwargs):
        assert host == "192.168.8.222"
        assert port == 10123
        saved_before_probe = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert saved_before_probe["host"] == "192.168.8.222"
        return {"udp_info_probe_result": "NOT_CONNECTED", "latency_ms": 12, "exception_type": None}

    monkeypatch.setattr(cli_module, "setup_info_probe", offline_probe)
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)
    panel = _execute_setup_payload(
        result,
        host="192.168.8.222",
        port_text="10123",
        label="Main Console",
        target_type="hardware",
        confirmation="save",
    )
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    reopened = _setup_state_from_current_config()

    assert saved["host"] == "192.168.8.222"
    assert saved["port"] == 10123
    assert saved["label"] == "Main Console"
    assert saved["intended_target_type"] == "hardware"
    assert "SETUP RESULT" in panel
    assert "CONFIGURATION" in panel
    assert "Saved" in panel and "true" in panel
    assert "Persistence verified" in panel and "true" in panel
    assert "CONNECTION VERIFICATION" in panel
    assert "Connection state" in panel and "unreachable" in panel
    assert "Endpoint verified" in panel and "false" in panel
    assert "Config not written" not in panel
    assert "Configuration was saved successfully." in panel
    assert reopened.current_values["host"] == "192.168.8.222"
    assert reopened.current_values["port"] == "10123"
    assert reopened.current_values["label"] == "Main Console"
    assert reopened.current_values["target_type"] == "hardware"


def test_setup_wrong_confirmation_retains_candidate_state_and_allows_save(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump({"schema_version": "1", "host": "192.168.8.88", "port": 10023, "intended_target_type": "unknown", "config_scope": "user"}), encoding="utf-8")
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)
    calls: list[dict[str, object]] = []

    def fake_setup_runtime(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "saved": True,
            "persistence_verified": True,
            "connected": False,
            "endpoint_verified": False,
            "status": "SAVED_NOT_CONNECTED",
            "configured_host": kwargs["host"],
            "configured_port": kwargs["port"],
            "attempted_path": "/info",
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }

    monkeypatch.setattr(cli_module, "setup_runtime", fake_setup_runtime)
    for wrong in ["", "S", "WRONG"]:
        before_calls = len(calls)
        state = SetupState(
            field_index=4,
            values={"host": "192.168.8.222", "port": "10123", "label": "Main Console", "target_type": "hardware"},
            current_text=wrong,
            current_values={"host": "192.168.8.88", "port": "10023", "target_type": "unknown"},
            config_path=str(config_path),
        )
        message, done = _advance_setup_state(state, result)
        assert done is False
        assert "Type SAVE to store this configuration or CANCEL to discard it." in message
        assert state.field_index == 4
        assert state.values["host"] == "192.168.8.222"
        assert state.values["port"] == "10123"
        assert state.values["label"] == "Main Console"
        assert state.values["target_type"] == "hardware"
        assert len(calls) == before_calls
        assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["host"] == "192.168.8.88"

        state.current_text = "Save"
        output, done = _advance_setup_state(state, result)
        assert done is True
        assert "SETUP RESULT" in output
        assert calls[-1]["host"] == "192.168.8.222"


def test_setup_cancel_preserves_old_config_and_skips_probe(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    original = {"schema_version": "1", "host": "192.168.8.88", "port": 10023, "intended_target_type": "unknown", "config_scope": "user"}
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)

    def forbidden_setup_runtime(**_kwargs):
        raise AssertionError("setup_runtime must not run on CANCEL")

    monkeypatch.setattr(cli_module, "setup_runtime", forbidden_setup_runtime)
    for confirmation in ("CANCEL", "cancel"):
        panel = _execute_setup_payload(
            result,
            host="192.168.8.222",
            port_text="10123",
            label="Main Console",
            target_type="hardware",
            confirmation=confirmation,
        )
        assert "Setup cancelled. Existing configuration was not changed." in panel
        assert "Read-only verification attempted" in panel and "false" in panel
        assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original


def test_get_info_uses_configured_endpoint_metadata_without_discovery_claim(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "host": "192.168.8.88",
                "port": 10023,
                "label": "FOH",
                "intended_target_type": "hardware",
                "config_scope": "user",
            }
        ),
        encoding="utf-8",
    )
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)

    def fake_get_info_runtime(**kwargs):
        return {
            "ok": False,
            "status": "NOT_CONNECTED",
            "message": "The configured endpoint did not respond to /info.",
            "configured_host": kwargs["host"],
            "configured_port": kwargs["port"],
            "attempted_path": "/info",
            "connected": False,
            "latency_ms": None,
            "data": {},
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }

    monkeypatch.setattr(cli_module, "get_info_runtime", fake_get_info_runtime)
    output, should_stop = execute_installer_command("/get-info", result)

    assert should_stop is False
    assert "CONFIGURED ENDPOINT" in output
    assert "192.168.8.88" in output
    assert "User configuration" in output
    assert "FOH" in output
    assert "Physical M32 console" in output
    assert "unavailable" in output
    assert "The configured endpoint did not respond to /info." in output
    assert "not discovered" in output


def test_verify_device_uses_intended_target_but_does_not_verify_hardware(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "host": "192.168.8.88",
                "port": 10023,
                "label": "FOH",
                "intended_target_type": "hardware",
                "config_scope": "user",
            }
        ),
        encoding="utf-8",
    )
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)
    captured = {}

    def fake_detect_device_runtime(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "status": "CONNECTED",
            "configured_host": kwargs["host"],
            "configured_port": kwargs["port"],
            "attempted_path": "/info",
            "connected": True,
            "classification": "CONNECTED_UNVERIFIED",
            "observed_target_type": "unknown",
            "hardware_verified": True,
            "production_live_ready": True,
            "osc_writes_sent": 0,
        }

    monkeypatch.setattr(cli_module, "detect_device_runtime", fake_detect_device_runtime)
    output, should_stop = execute_installer_command("/verify-device", result)

    assert should_stop is False
    assert captured["target_type"] == "hardware"
    assert "Physical M32 console" in output
    assert "Hardware verified" in output and "false" in output
    assert "Production ready" in output and "false" in output
    assert "Intended target describes operator expectation only." in output
    assert "Network scan" in output and "not_run" in output


def test_panel_scroll_preserves_last_content_line_and_reports_end_state(tmp_path):
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path / "home")
    panel = [f"status line {idx}" for idx in range(1, 31)] + ["Production ready          : false"]

    _, body, footer = render_frame(
        "posix",
        result,
        dry_run=True,
        color=False,
        width=82,
        height=12,
        panel_lines=panel,
        panel_offset=999,
        view="status",
    )

    body_text = "\n".join(strip_ansi(row) for row in body)
    assert "Production ready          : false" in body_text
    assert "End of status" in strip_ansi(footer)
    assert _next_panel_offset(0, len(panel), 12, "DOWN") == 1
    assert _next_panel_offset(5, len(panel), 12, "UP") == 4


def test_mcp_config_command_visible_and_allowed_aliases():
    assert "/mcp-config" in COMMAND_REGISTRY
    assert COMMAND_REGISTRY["/mcp-config"]["desc"] == "Generate safe MCP client configuration and setup guidance"
    assert parse_installer_command("/mcp-config") == "/mcp-config"
    assert parse_installer_command("m32-bridge mcp-config") == "/mcp-config"
    assert parse_installer_command("m32-bridge mcp-config --client claude") is None
    assert parse_installer_command("m32-bridge mcp-config | tee config.json") is None


def test_mcp_config_tty_page_is_responsive_ansi_safe_and_reaches_end(tmp_path, monkeypatch):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance, render_mcp_guidance_text

    monkeypatch.setenv("HOME", str(tmp_path))
    payload = render_mcp_guidance(environ={}, home=tmp_path, os_family="linux", version=application_version())
    expected_launcher = str(tmp_path / ".local" / "bin" / "m32-bridge")

    assert payload["launcher_path"] == expected_launcher
    assert payload["args"] == ["mcp-server"]
    assert payload["environment_required"] == {}
    assert payload["automatic_client_config_write"] is False
    assert payload["osc_writes_sent"] == 0
    assert payload["network_scan"] is False
    assert payload["console_probe"] == "not_run"

    for width in (120, 100, 80, 60, 50):
        text = render_mcp_guidance_text(payload, width=width)
        coloured = "\n".join(
            execute_installer_command(
                "/mcp-config",
                build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path),
                color=True,
                width=width,
            )[0].splitlines()
        )
        plain = strip_ansi(coloured)
        assert_ansi_integrity(coloured)
        assert "MCP CLIENT SETUP" in text
        for section in [
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
        ]:
            assert section in text
        assert "m32-bridge" in text
        assert ".venv" not in text
        assert "python -m" not in text
        assert "httpUrl" not in text
        assert "Direct local stdio connection : not available" in text
        assert "End of MCP client setup" in text
        assert "MCP CLIENT SETUP" in plain


def test_mcp_config_panel_footer_and_last_line_preserved(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance, render_mcp_guidance_text

    payload = render_mcp_guidance(environ={}, home=tmp_path, os_family="linux", version=application_version())
    panel = render_mcp_guidance_text(payload, width=60).splitlines()
    assert len(panel) > 12

    window, footer = _panel_window(panel, 999, 8, view="mcp")

    assert window[-1] == "End of MCP client setup"
    assert "End of MCP setup" in footer
    assert "End of panel" not in footer


def test_mcp_panel_views_and_command_routing_stay_consistent(tmp_path):
    for view in ("help", "contact", "status", "panel", "action", "setup", "mcp"):
        assert view in PANEL_VIEWS
    assert _view_for_command("/mcp-config") == "mcp"
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path / "home")
    assert "Up/Down/PgUp/PgDn Scroll" in strip_ansi(render_footer_status(result, view="mcp"))


def test_mcp_config_direct_frame_uses_full_panel_and_specific_footer(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance, render_mcp_guidance_text

    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path / "home")
    payload = render_mcp_guidance(environ={}, home=tmp_path, os_family="linux", version=application_version())
    panel = render_mcp_guidance_text(payload, width=100).splitlines()

    header, body, footer = render_frame(
        "posix",
        result,
        dry_run=True,
        color=False,
        width=100,
        height=30,
        panel_lines=panel,
        panel_offset=0,
        view="mcp",
    )
    body_text = "\n".join(strip_ansi(row) for row in body)
    assert "MCP CLIENT SETUP" in body_text
    assert "SYSTEM" not in body_text
    assert "More below" in strip_ansi(footer)
    assert strip_ansi(body[-1]).startswith("root/ $ ")
    assert len([*header, *body, footer]) == 30

    _, end_body, end_footer = render_frame(
        "posix",
        result,
        dry_run=True,
        color=False,
        width=100,
        height=30,
        panel_lines=panel,
        panel_offset=999,
        view="mcp",
    )
    end_text = "\n".join(strip_ansi(row) for row in end_body)
    assert "End of MCP client setup" in end_text
    assert "End of MCP setup" in strip_ansi(end_footer)
    assert "End of panel" not in strip_ansi(end_footer)


def test_command_loop_renders_and_scrolls_mcp_config_fullscreen(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    mcp_index = next(index for index, item in enumerate(SLASH_COMMANDS) if item["cmd"] == "/mcp-config")
    keys = iter(["/", *(["DOWN"] * mcp_index), "ENTER", *(["PAGEDOWN"] * 20), "ESC", "ESC"])

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
        size_provider=lambda: (100, 30),
    )

    combined = sink.data + transcript
    for expected in ("MCP CLIENT SETUP", "INSTALLATION", "CLAUDE DESKTOP", "GEMINI CLI", "CHATGPT"):
        assert expected in combined
    assert "End of MCP setup" in combined
    assert "> /mcp-config" in strip_ansi(combined)
    assert "\x1b[?7h" in combined
    assert "\x1b[?25h" in combined
    assert "\x1b[r" in combined


def test_final_readme_mcp_guide_contract_and_development_only_python_m(tmp_path):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.startswith("# X32-Bridge MCP")
    assert "Powered by DXBMARK LLC" in readme
    for section in [
        "## What It Is",
        "## Current Version",
        "## Installation",
        "## First Run",
        "## Runtime Configuration",
        "## Running the MCP Server",
        "## MCP Client Setup",
        "### Claude Desktop",
        "### Codex",
        "### Gemini CLI",
        "### Antigravity",
        "### ChatGPT",
        "### Other / Generic MCP Clients",
        "## Why No Host/Port in Client Config",
        "## Environment Variables",
        "## Commands",
        "## TTY Commands",
        "## Safety Model",
        "## Troubleshooting",
        "## Development-Only Setup",
        "## Support",
    ]:
        assert section in readme
    assert "m32-bridge mcp-config" in readme
    assert "/mcp-config" in readme
    assert "`SAVE` stores the configuration first" in readme
    assert "configuration remains saved" in readme
    assert "Direct local stdio is not available in ChatGPT" in readme
    assert "Do not create a localhost URL, public tunnel, OAuth flow, webhook, or port-forwarding setup" in readme
    assert ".venv" not in readme

    development_section = readme.split("## Development-Only Setup", 1)[1]
    normal_section = readme.split("## Development-Only Setup", 1)[0]
    assert "python -m m32_bridge mcp-server" in development_section
    assert "python -m" not in normal_section
    assert "saves after success" not in readme.lower()
    assert "save only after successful" not in readme.lower()
    assert "probe then save" not in readme.lower()


def test_help_reformatted_without_layout_markers_and_with_field_guide():
    for width in [120, 80, 50]:
        help_text = installer_help_text(width=width)
        assert "TWO-COLUMN HELP" not in help_text
        assert "ONE-COLUMN HELP" not in help_text
        assert "COMPACT HELP" not in help_text
        for section in ["USAGE", "OPTIONS", "COMMANDS", "NAVIGATION", "CONFIGURATION", "SAFETY", "FIELD GUIDE"]:
            assert section in help_text
        assert "/verify-device" in help_text
        assert "m32-bridge detect-device" in help_text
        assert "/mcp-config" in help_text


def assert_ansi_integrity(output: str):
    plain = strip_ansi(output)
    assert "\x1b" not in plain
    assert "48;2" not in plain
    assert "38;2" not in plain
    assert "[0m" not in plain
    assert "[1m" not in plain


def _semantic_lines(text: str) -> list[str]:
    return [line.rstrip() for line in strip_ansi(text).splitlines() if line.strip()]


def test_help_color_ansi_integrity_across_widths():
    required_sections = ["INSTALLER HELP", "USAGE", "OPTIONS", "INSTALL SELECTION", "COMMANDS", "NAVIGATION", "CONFIGURATION", "SAFETY", "FIELD GUIDE", "CONTACT"]
    required_commands = ["/help", "/health", "/setup", "/get-info", "/verify-device", "/doctor-runtime", "/mcp-config", "/status", "/contact", "/clear", "/exit"]
    for width in (120, 100, 80, 60, 50):
        coloured = installer_help_text(color=True, width=width)
        plain = installer_help_text(color=False, width=width)
        assert "\x1b[" in coloured
        assert "\x1b[" not in plain
        assert_ansi_integrity(coloured)
        assert _semantic_lines(coloured) == _semantic_lines(plain)
        assert strip_ansi(coloured).count("INSTALLER HELP") == 1
        for section in required_sections:
            assert section in strip_ansi(coloured)
        for command in required_commands:
            assert command in strip_ansi(coloured)
        assert "TWO-COLUMN HELP" not in strip_ansi(coloured)
        assert "ONE-COLUMN HELP" not in strip_ansi(coloured)
        assert "COMPACT HELP" not in strip_ansi(coloured)


def test_product_identity_banner_version_and_contact_are_responsive():
    result = build_install_result(surface="posix", platform="linux", dry_run=True)
    rendered = render_tty_installer("posix", result, dry_run=True)

    expected_version = read_project_version(ROOT / "pyproject.toml")

    assert BANNER in rendered
    assert POWERED_BY in rendered
    assert "DXBMARK M32 BRIDGE INSTALLER" not in rendered
    assert application_version() == expected_version
    assert COMMAND_REGISTRY["/contact"]["desc"] == "Show product information, version, publisher and support"

    for width in (120, 80, 50):
        contact = installer_contact_text(color=True, width=width)
        plain = strip_ansi(contact)
        assert_ansi_integrity(contact)
        assert "X32-BRIDGE MCP" in plain
        assert "PRODUCT" in plain
        assert "Version" in plain and expected_version in plain
        assert PACKAGE_NAME in plain
        assert CLI_NAME in plain
        assert "PURPOSE" in plain
        assert "SAFETY MODEL" in plain
        assert "POWERED BY" in plain
        assert CONTACT_PHONE in plain
        assert "End of product information" in plain
        assert "production readiness" not in plain.lower()


def test_help_frame_level_accesses_last_content_without_ansi_fragments(tmp_path):
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path / "home")
    for width, height in [(120, 36), (100, 30), (80, 24), (60, 20), (50, 16)]:
        panel = installer_help_text(color=True, width=width).splitlines()
        header, body, footer = render_frame(
            "posix",
            result,
            dry_run=True,
            color=True,
            width=width,
            height=height,
            panel_lines=panel,
            panel_offset=0,
            view="help",
        )
        assert len([*header, *body, footer]) == height
        first_text = "\n".join(strip_ansi(row) for row in body)
        assert_ansi_integrity(first_text)
        assert "USAGE" in first_text
        max_offset = 0
        for _ in range(20):
            max_offset = _next_panel_offset(max_offset, len(panel), height, "PAGEDOWN")
        _, end_body, end_footer = render_frame(
            "posix",
            result,
            dry_run=True,
            color=True,
            width=width,
            height=height,
            panel_lines=panel,
            panel_offset=max_offset,
            view="help",
        )
        end_text = "\n".join(strip_ansi(row) for row in end_body)
        assert_ansi_integrity(end_text)
        assert "End of help" in strip_ansi(end_footer) or "Lines" in strip_ansi(end_footer)
        assert CONTACT_PHONE in end_text or "Shell alias" in end_text or "Save" in end_text


def test_target_type_selector_preserves_current_and_supports_up_down_numeric(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    for target_type, expected_label in [
        ("hardware", "Physical M32 console"),
        ("emulator", "Emulator / test endpoint"),
        ("unknown", "Unknown / not declared"),
    ]:
        config_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1",
                    "host": "192.168.8.88",
                    "port": 10023,
                    "intended_target_type": target_type,
                    "config_scope": "user",
                }
            ),
            encoding="utf-8",
        )
        state = _setup_state_from_current_config()
        state.field_index = 3
        rendered = "\n".join(_setup_state_lines(state))
        assert f"> {['hardware', 'emulator', 'unknown'].index(target_type) + 1}. {expected_label}" in rendered
        assert state.values == {}

    state = SetupState(field_index=3, current_values={"target_type": "unknown"}, target_type_index=2)
    _move_setup_target_selector(state, "DOWN")
    assert state.values["target_type"] == "hardware"
    _move_setup_target_selector(state, "UP")
    assert state.values["target_type"] == "unknown"
    assert _select_setup_target_numeric(state, "1") is True
    assert state.values["target_type"] == "hardware"
    assert _select_setup_target_numeric(state, "2") is True
    assert state.values["target_type"] == "emulator"
    assert _select_setup_target_numeric(state, "3") is True
    assert state.values["target_type"] == "unknown"
    assert _select_setup_target_numeric(state, "x") is False
    assert state.values["target_type"] == "unknown"


def test_target_type_selector_enter_review_and_no_write_before_save(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    config_path = default_user_config_path()
    config_path.parent.mkdir(parents=True)
    original = {
        "schema_version": "1",
        "host": "192.168.8.88",
        "port": 10023,
        "intended_target_type": "unknown",
        "config_scope": "user",
    }
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=home)
    state = _setup_state_from_current_config()
    state.values = {"host": "192.168.8.88", "port": "10023", "label": ""}
    state.field_index = 3
    assert _select_setup_target_numeric(state, "1") is True
    output, done = _advance_setup_state(state, result)
    review = "\n".join(_setup_state_lines(state))

    assert output is None
    assert done is False
    assert state.field_index == 4
    assert state.values["target_type"] == "hardware"
    assert "Physical M32 console" in review
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original


def test_main_dashboard_system_row_includes_version_architecture_and_shell(tmp_path):
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path / "home")

    text = render_tty_installer("posix", result, dry_run=True)

    assert "Platform" in text
    assert "Architecture" not in text
    assert "Shell" not in text
    assert "·" in text
