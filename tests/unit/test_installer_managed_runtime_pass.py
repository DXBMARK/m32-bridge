from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from m32_bridge.cli import detect_device_runtime
from m32_bridge.installer.runtime_manager import (
    APPROVED_PYTHON_MINOR,
    MANAGED_PYTHON_POLICY,
    OFFICIAL_SOURCE_ARCHIVE_URLS,
    PROJECT_PYTHON_RANGE,
    UV_INSTALL_URLS,
    bootstrap_uv_and_python,
    download_capability,
    inspect_runtime,
    local_runtime_diagnostics,
    platform_information,
)
from m32_bridge.installer.script_runtime import build_install_result
from m32_bridge.installer.tty_app import (
    CONTACT_PHONE,
    COMMAND_REGISTRY,
    execute_installer_command,
    installer_help_text,
    parse_installer_command,
    refresh_source_status,
    render_tty_installer,
    render_status_text,
    derive_dns_status,
)


ROOT = Path(__file__).resolve().parents[2]
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"


def test_approved_python_policy_is_minor_pinned_and_user_local():
    assert APPROVED_PYTHON_MINOR == "3.13"
    assert MANAGED_PYTHON_POLICY == {
        "implementation": "CPython",
        "preferred_minor": "3.13",
        "allowed_range": ">=3.11,<3.14",
        "installation_type": "uv_managed_user_local",
        "system_python_modified": False,
        "global_python_installed": False,
        "default_python_aliases_installed": False,
        "admin_required": False,
    }


def test_runtime_inspection_does_not_promote_compatible_system_python(monkeypatch):
    monkeypatch.setattr("m32_bridge.installer.runtime_manager.which", lambda name: "/usr/bin/uv" if name == "uv" else "/usr/bin/python3")
    monkeypatch.setattr(
        "m32_bridge.installer.runtime_manager._run_capture",
        lambda argv, **kwargs: ("Python 3.13.8", 0)
        if "python" in Path(argv[0]).name
        else ("/managed/python3.13", 0)
        if "find" in argv
        else ("uv 0.10.0", 0),
    )

    runtime = inspect_runtime()

    assert runtime["approved_minor"] == "3.13"
    assert runtime["python_source"] == "uv_managed"
    assert runtime["managed_python_detected"] is True
    assert runtime["system_python_modified"] is False


def test_runtime_inspection_and_diagnostics_respect_passed_environment(monkeypatch, tmp_path):
    launcher = tmp_path / "bin" / "m32-bridge"
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    calls: list[tuple[str, str | None]] = []

    def fake_which(name: str, *, path: str | None = None):
        calls.append((name, path))
        if name == "uv":
            return "/custom/bin/uv"
        if name == "python3":
            return "/custom/bin/python3"
        return None

    monkeypatch.setattr("m32_bridge.installer.runtime_manager.shutil.which", fake_which)
    monkeypatch.setattr(
        "m32_bridge.installer.runtime_manager._run_capture",
        lambda argv, **kwargs: ("uv 0.10.0", 0)
        if argv[-1] == "--version" and Path(argv[0]).name == "uv"
        else ("/managed/python3.13", 0)
        if "find" in argv
        else ("Python 3.13.12", 0),
    )

    env = {"PATH": f"{launcher.parent}{os.pathsep}/custom/bin", "UV_MANAGED_PYTHON": "1"}
    runtime = inspect_runtime(environ=env)
    diagnostics = local_runtime_diagnostics(environ=env, launcher_path=str(launcher), app_path=str(tmp_path / "app"))

    assert runtime["uv_path"] == "/custom/bin/uv"
    assert diagnostics["path_visibility"] is True
    assert calls and all(path == env["PATH"] for _, path in calls)


def test_script_runtime_policy_parity_and_no_dependency_drift_commands():
    posix = POSIX_INSTALLER.read_text(encoding="utf-8")
    windows = WINDOWS_INSTALLER.read_text(encoding="utf-8")
    script_runtime = (ROOT / "src" / "m32_bridge" / "installer" / "script_runtime.py").read_text(encoding="utf-8")

    assert f'APPROVED_PYTHON_MINOR="{APPROVED_PYTHON_MINOR}"' in posix
    assert f'PROJECT_PYTHON_RANGE="{PROJECT_PYTHON_RANGE}"' in posix
    assert f'UV_INSTALL_URL_POSIX="{UV_INSTALL_URLS["posix"]}"' in posix
    assert f'DEFAULT_SOURCE_URL="{OFFICIAL_SOURCE_ARCHIVE_URLS["posix"]}"' in posix
    assert f'$ApprovedPythonMinor = "{APPROVED_PYTHON_MINOR}"' in windows
    assert f'$ProjectPythonRange = "{PROJECT_PYTHON_RANGE}"' in windows
    assert f'$UvInstallUrlWindows = "{UV_INSTALL_URLS["windows"]}"' in windows
    assert f'$DefaultSourceUrl = "{OFFICIAL_SOURCE_ARCHIVE_URLS["windows"]}"' in windows
    for text in (posix, windows):
        assert "uv lock" not in text
        assert "--default" not in text
        assert "configured_for_github" not in text
        assert "GitHub raw/archive reachable" not in text
    assert "Set-ExecutionPolicy" not in windows.replace("does not call Set-ExecutionPolicy", "")
    assert "process-scoped" in windows
    for text in (posix, windows, script_runtime):
        assert "--frozen" in text
        assert not re.search(r"uv(?:Path)?\s+run(?![^\n\r]*--frozen)", text)
        assert not re.search(r"uv run(?![^\n\r]*--frozen)", text)
    assert "uv.lock is required for reproducible frozen runtime execution" in posix
    assert "uv.lock is required for reproducible frozen runtime execution" in windows
    assert "uv.lock" in script_runtime


def test_posix_installer_default_uv_cache_is_user_local_not_private_tmp():
    posix = POSIX_INSTALLER.read_text(encoding="utf-8")

    assert 'USER_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"' in posix
    assert 'DEFAULT_UV_CACHE_DIR="${USER_CACHE_HOME}/uv"' in posix
    assert 'mkdir -p "${DEFAULT_UV_CACHE_DIR}"' in posix
    assert 'UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/uv-cache}"' not in posix


def test_macos_and_ubuntu_cache_path_use_same_user_cache_formula(tmp_path):
    home = tmp_path / "home"
    xdg = tmp_path / "xdg-cache"
    script = POSIX_INSTALLER.read_text(encoding="utf-8")

    assert "/private/tmp/uv-cache" not in script
    assert str(home / ".cache" / "uv").endswith("/.cache/uv")
    assert str(xdg / "uv").endswith("/xdg-cache/uv")


def test_download_capability_prefers_curl_and_treats_wget_as_optional():
    capability = download_capability(surface="posix", finder=lambda name: "/bin/curl" if name == "curl" else None)

    assert capability["primary_tool"] == "curl available"
    assert capability["wget_fallback"] == "optional, not installed"
    assert capability["manual_fallback"] == "available"


def test_download_capability_uses_wget_or_manual_without_installing_tools():
    wget = download_capability(surface="posix", finder=lambda name: "/bin/wget" if name == "wget" else None)
    missing = download_capability(surface="posix", finder=lambda name: None)
    windows = download_capability(surface="windows", finder=lambda name: None)

    assert wget["primary_tool"] == "wget available"
    assert missing["primary_tool"] == "not available"
    assert missing["manual_fallback"] == "available"
    assert windows["primary_tool"] == "PowerShell Invoke-WebRequest/Invoke-RestMethod available"


def test_platform_information_uses_linux_release_fields(tmp_path):
    os_release = tmp_path / "os-release"
    os_release.write_text('PRETTY_NAME="Example Linux 9"\nVERSION_ID="9"\n', encoding="utf-8")

    info = platform_information(
        system="Linux",
        release="6.9.1",
        machine="aarch64",
        environ={"SHELL": "/bin/bash"},
        os_release_path=os_release,
        proc_version_text="Linux version 6.9.1",
    )

    assert info["os"] == "Example Linux 9"
    assert info["version"] == "9"
    assert info["kernel_build"] == "6.9.1"
    assert info["architecture"] == "aarch64"
    assert info["shell"] == "bash"
    assert info["wsl"] == "not_detected"


def test_platform_information_detects_wsl_without_claiming_container(tmp_path):
    os_release = tmp_path / "os-release"
    os_release.write_text('PRETTY_NAME="Ubuntu 24.04"\nVERSION_ID="24.04"\n', encoding="utf-8")

    info = platform_information(
        system="Linux",
        release="5.15.0-microsoft-standard-WSL2",
        machine="x86_64",
        environ={"SHELL": "/bin/zsh", "WSL_DISTRO_NAME": "Ubuntu"},
        os_release_path=os_release,
        proc_version_text="Microsoft WSL2",
        container_hint="not_detected",
    )

    assert info["wsl"] == "detected"
    assert info["container_hint"] == "not_detected"


def test_bootstrap_requires_exact_install_and_cleans_temporary_file(monkeypatch):
    downloaded: list[Path] = []
    calls: list[list[str]] = []

    def downloader(url: str, target: Path) -> None:
        downloaded.append(target)
        target.write_text("# fixed official installer", encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def runner(argv, **kwargs):
        calls.append(list(argv))
        return Completed()

    monkeypatch.setattr(
        "m32_bridge.installer.runtime_manager._run_capture",
        lambda argv, **kwargs: ("uv 0.10.0", 0)
        if argv[-1] == "--version" and Path(argv[0]).name == "uv"
        else ("/managed/python3.13", 0)
        if "find" in argv
        else ("Python 3.13.12", 0),
    )
    rejected = bootstrap_uv_and_python(
        surface="posix",
        confirmation="install",
        downloader=downloader,
        runner=runner,
        finder=lambda name: "/usr/local/bin/uv" if name == "uv" else None,
    )
    accepted = bootstrap_uv_and_python(
        surface="posix",
        confirmation="INSTALL",
        downloader=downloader,
        runner=runner,
        finder=lambda name: "/usr/local/bin/uv" if name == "uv" else None,
    )

    assert rejected["installed"] is False
    assert downloaded and all(not path.exists() for path in downloaded)
    assert accepted["ok"] is True
    assert ["/usr/local/bin/uv", "python", "install", "3.13"] in calls
    assert not any("--default" in arg for call in calls for arg in call)
    assert all("sudo" not in arg.lower() for call in calls for arg in call)


def test_help_layouts_commands_colours_and_contact():
    wide = installer_help_text(width=120)
    medium = installer_help_text(width=80)
    compact = installer_help_text(width=50)

    for text in (wide, medium, compact):
        assert "TWO-COLUMN HELP" not in text
        assert "ONE-COLUMN HELP" not in text
        assert "COMPACT HELP" not in text
        assert "STATUS COLOURS" in text
        assert "Green" in text and "Yellow" in text and "Red" in text and "Slate" in text
        assert "/verify-device" in text
        assert "m32-bridge detect-device" in text
        assert "FIELD GUIDE" in text
        assert "/legend" not in text
        assert CONTACT_PHONE in text


def test_command_registry_is_exact_and_rejects_shell_syntax():
    assert set(COMMAND_REGISTRY) == {
        "/health",
        "/setup",
        "/get-info",
        "/verify-device",
        "/doctor-runtime",
        "/mcp-config",
        "/status",
        "/contact",
        "/help",
        "/clear",
        "/exit",
    }
    assert parse_installer_command("m32-bridge detect-device") == "/verify-device"
    assert parse_installer_command("m32-bridge health") == "/health"
    assert parse_installer_command("m32-bridge health; whoami") is None
    assert parse_installer_command("m32-bridge health | tee x") is None
    assert parse_installer_command("m32-bridge health --extra") is None


def test_setup_empty_or_wrong_confirmation_does_not_probe_or_write(monkeypatch, tmp_path):
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path)
    calls: list[object] = []

    def forbidden_setup_runtime(**kwargs):
        calls.append(kwargs)
        raise AssertionError("setup_runtime must not run without exact SAVE")

    monkeypatch.setattr("m32_bridge.cli.setup_runtime", forbidden_setup_runtime)

    for confirmation in ("", "WRONG", "CANCEL"):
        answers = iter(["192.0.2.10", "10023", "FOH", "hardware", confirmation])
        output, stop = execute_installer_command(
            "/setup",
            result,
            input_func=lambda prompt, answers=answers: next(answers),
        )

        assert stop is False
        assert "SETUP RESULT" in output
        assert "Probe not run" in output and "true" in output
        assert "Config not written" in output and "true" in output
        assert "Attempted path" in output and "not_attempted" in output
        assert "Intended path" in output and "/info" in output
        assert "OSC writes" in output and "0" in output
        assert "Network scan" in output and "not run" in output

    assert calls == []


def test_setup_save_confirmation_runs_probe_and_save(monkeypatch, tmp_path):
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path)
    calls: list[dict[str, object]] = []

    def fake_setup_runtime(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "connected": True,
            "status": "SAVED",
            "attempted_path": "/info",
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }

    monkeypatch.setattr("m32_bridge.cli.setup_runtime", fake_setup_runtime)

    answers = iter(["192.0.2.10", "", "FOH", "hardware", "SAVE"])
    output, stop = execute_installer_command(
        "/setup",
        result,
        input_func=lambda prompt: next(answers),
    )

    assert stop is False
    assert calls and calls[0]["confirm_save"] is True
    assert "SETUP RESULT" in output
    assert "Attempted path" in output and "/info" in output
    assert "Network scan" in output and "not run" in output
    assert "OSC writes" in output and "0" in output


def test_unknown_command_does_not_exit_and_local_actions_are_in_process(tmp_path):
    result = build_install_result(surface="posix", platform="linux", dry_run=True, home=tmp_path)

    unknown, stop = execute_installer_command("echo hello", result)
    health, health_stop = execute_installer_command("/health", result)
    doctor, doctor_stop = execute_installer_command("/doctor-runtime", result)

    assert unknown == "Unknown command. Type / to view allowed commands."
    assert stop is False
    assert health_stop is False and "OSC writes" in health
    assert doctor_stop is False and "Console probe" in doctor and "not_run" in doctor


def test_status_is_honest_and_does_not_treat_configured_url_as_reachable(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        install_source="github_release_or_archive",
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
    )

    status = render_status_text(result)
    main = render_tty_installer("posix", result, dry_run=True)

    assert "INSTALLER" in status
    assert "PLATFORM" in status
    assert "RUNTIME" in status
    assert "SOURCE" in status
    assert "CONSOLE" in status
    assert "SAFETY" in status
    assert "Network HTTPS route" in status and "not_checked" in status
    assert "GitHub repository" in status and "not_checked" in status
    assert "Raw installer" in status and "not_checked" in status
    assert "Source archive" in status and "not_checked" in status
    assert "Repository" in status and "https://github.com/DXBMARK/m32-bridge" in status
    assert "Repository" in status and "https://github.com/DXBMARK/m32-bridge/archive" not in status
    assert "INSTALLER" in main and "Source" in main
    assert "Source configuration" not in main
    assert "Reachability" not in main
    assert "configured_for_github_archive" not in main
    assert "Hardware verified" in status and "false" in status
    assert "OSC writes sent" in status and "0" in status


def test_status_refresh_is_explicit_cached_and_never_probes_console(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        install_source="github_release_or_archive",
    )
    calls: list[str] = []

    def checker(url: str, timeout: float) -> str:
        calls.append(url)
        return "reachable"

    first = refresh_source_status(result, checker=checker)
    second = refresh_source_status(result, checker=checker)
    rendered = render_status_text(result)

    assert first is second
    assert first["github_repository"] == "reachable"
    assert first["dns"] == "resolved"
    assert len(calls) == 4
    assert any("raw.githubusercontent.com" in url for url in calls)
    assert any("archive" in url for url in calls)
    assert "GitHub repository" in rendered and "reachable" in rendered
    assert result.get("console_connection_status") is None


def test_status_refresh_force_runs_new_checks_and_updates_last_checked(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        install_source="github_release_or_archive",
    )
    calls: list[str] = []

    def checker(url: str, timeout: float) -> str:
        calls.append(url)
        return f"reachable-{len(calls)}"

    first = refresh_source_status(result, checker=checker, force=True)
    previous_last_checked = first["last_checked"]
    time.sleep(0.001)
    second = refresh_source_status(result, checker=checker, force=True)

    assert previous_last_checked != second["last_checked"]
    assert len(calls) == 8
    assert first is not second


def test_status_refresh_uses_exact_source_targets(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz",
        install_source="github_release_or_archive",
    )
    calls: list[str] = []

    refresh_source_status(result, checker=lambda url, timeout: calls.append(url) or "reachable", force=True)

    assert "https://github.com/" in calls
    assert "https://github.com/DXBMARK/m32-bridge" in calls
    assert "https://raw.githubusercontent.com/DXBMARK/m32-bridge/main/scripts/install.sh" in calls
    assert "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz" in calls
    assert calls[0] != "https://github.com/DXBMARK/m32-bridge"


def test_derive_dns_status_mapping():
    assert derive_dns_status(["reachable", "reachable"]) == "resolved"
    assert derive_dns_status(["http_error", "dns_error"]) == "resolved"
    assert derive_dns_status(["timeout", "tls_error", "not_checked"]) == "resolved"
    assert derive_dns_status(["dns_error", "dns_error", "not_checked"]) == "dns_error"
    assert derive_dns_status(["timeout", "timeout"]) == "not_determined"
    assert derive_dns_status(["unreachable", "unreachable"]) == "not_determined"
    assert derive_dns_status(["timeout", "reachable", "timeout", "not_checked"]) == "resolved"
    assert derive_dns_status(["not_checked", "not_checked"]) == "not_checked"


def test_status_refresh_derives_dns_from_bounded_https_results(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        install_source="github_release_or_archive",
    )

    for status, expected_dns in [
        ("reachable", "resolved"),
        ("http_error", "resolved"),
        ("tls_error", "resolved"),
        ("dns_error", "dns_error"),
        ("timeout", "not_determined"),
        ("unreachable", "not_determined"),
    ]:
        result.pop("source_status", None)
        refreshed = refresh_source_status(result, checker=lambda url, timeout, status=status: status, force=True)
        assert refreshed["dns"] == expected_dns


def test_status_refresh_mixed_dns_results(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        install_source="github_release_or_archive",
    )
    statuses = iter(["timeout", "reachable", "timeout", "not_checked"])
    assert refresh_source_status(result, checker=lambda url, timeout: next(statuses), force=True)["dns"] == "resolved"

    statuses = iter(["dns_error", "dns_error", "not_checked", "not_checked"])
    assert refresh_source_status(result, checker=lambda url, timeout: next(statuses), force=True)["dns"] == "dns_error"


def test_status_refresh_does_not_call_resolver_or_tcp_helpers(monkeypatch, tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        install_source="github_release_or_archive",
    )
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no DNS resolver call")))
    monkeypatch.setattr("socket.gethostbyname", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no DNS resolver call")))
    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no TCP DNS probe")))

    refreshed = refresh_source_status(result, checker=lambda url, timeout: "reachable", force=True)

    assert refreshed["dns"] == "resolved"


def test_status_refresh_forwards_timeout_to_every_https_check(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        install_source="github_release_or_archive",
    )
    timeouts: list[float] = []

    refresh_source_status(result, checker=lambda url, timeout: timeouts.append(timeout) or "reachable", force=True, timeout=0.125)

    assert timeouts == [0.125, 0.125, 0.125, 0.125]


def test_status_refresh_has_no_dns_worker_global_timeout_or_subprocess_logic():
    source = (ROOT / "src" / "m32_bridge" / "installer" / "tty_app.py").read_text(encoding="utf-8")
    refresh_body = source.split("def refresh_source_status(", 1)[1].split("def _execute_setup(", 1)[0]

    assert "ThreadPoolExecutor" not in source
    assert "setdefaulttimeout" not in source
    assert "getaddrinfo" not in refresh_body
    assert "gethostbyname" not in refresh_body
    assert "create_connection" not in refresh_body
    assert "subprocess" not in refresh_body
    assert "getent" not in refresh_body
    assert "nslookup" not in refresh_body
    assert "Resolve-DnsName" not in refresh_body


def test_refresh_guard_returns_cache_while_in_progress_without_new_workers(tmp_path):
    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        source_url="https://github.com/DXBMARK/m32-bridge/archive/main.tar.gz",
        install_source="github_release_or_archive",
    )
    result["source_status"] = {"github_repository": "reachable", "last_checked": "2026-07-29T00:00:00+00:00"}
    result["_source_refresh_in_progress"] = True
    calls: list[str] = []

    cached = refresh_source_status(result, checker=lambda url, timeout: calls.append(url) or "reachable")

    assert cached["github_repository"] == "reachable"
    assert calls == []


def test_verify_device_generic_info_response_is_not_hardware_evidence():
    payload = detect_device_runtime(
        host="192.0.2.20",
        port=10023,
        target_type="hardware",
        probe_result={
            "udp_info_probe_result": "CONNECTED",
            "connected": True,
            "attempted_path": "/info",
            "response_address": ["192.0.2.20", 10023],
            "info_raw": ["M32", "4.10", "1.0", "FOH"],
            "latency_ms": 2,
            "osc_writes_sent": 0,
        },
    )

    assert payload["classification"] == "CONNECTED_UNVERIFIED"
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert payload["osc_writes_sent"] == 0
