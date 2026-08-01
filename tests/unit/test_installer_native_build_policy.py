from __future__ import annotations

import stat
from pathlib import Path

import pytest

from m32_bridge.installer import script_runtime
from m32_bridge.installer.runtime_manager import RuntimeManagerState


def _install_result(tmp_path: Path, *, platform: str = "linux", architecture: str = "x86_64"):
    result = script_runtime.build_install_result(
        surface="posix",
        platform=platform,
        dry_run=False,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="installed_user_local"),
    )
    result.update({"bootstrap_apply": True, "architecture": architecture})
    return result


def _fake_uv(tmp_path: Path, body: str) -> Path:
    uv_bin = tmp_path / "bin" / "uv"
    uv_bin.parent.mkdir(parents=True, exist_ok=True)
    uv_bin.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    uv_bin.chmod(0o755)
    return uv_bin


def test_production_runtime_argv_forbids_builds_and_skips_root_project(monkeypatch, tmp_path):
    log = tmp_path / "uv-argv.log"
    uv_bin = _fake_uv(
        tmp_path,
        "printf '%s\\n' \"$*\" >> \"$FAKE_UV_ARGV\"\n"
        "app=''\nprevious=''\n"
        "for value in \"$@\"; do [ \"$previous\" = '--directory' ] && app=$value; previous=$value; done\n"
        "case \" $* \" in\n"
        "  *' sync '*) mkdir -p \"$app/.venv\" ;;\n"
        "  *'platform.python_version'*) printf '%s\\n' '3.13.12' ;;\n"
        "  *'import yaml, mcp, pydantic, m32_bridge'*) printf '%s\\n' 'READY' ;;\n"
        "esac\n",
    )
    monkeypatch.setenv("FAKE_UV_ARGV", str(log))
    result = _install_result(tmp_path / "home")

    applied = script_runtime.perform_apply_install("posix", result, uv_bin=str(uv_bin))

    calls = log.read_text(encoding="utf-8").splitlines()
    assert applied["ok"] is True
    assert len(calls) == 3
    assert all("--frozen" in call and "--managed-python" in call and "--python 3.13" in call for call in calls)
    assert all("--no-build" in call for call in calls)
    assert "--no-install-project" in calls[0]
    assert all("--no-sync" in call for call in calls[1:])
    assert not any(token in " ".join(calls).lower() for token in ("maturin", "cargo", "rustup", " gcc", " clang", " cc"))


def test_missing_locked_wheel_is_controlled_and_full_output_goes_to_private_log(monkeypatch, tmp_path, capsys):
    uv_bin = _fake_uv(
        tmp_path,
        "case \" $* \" in\n"
        "  *' sync '*)\n"
        "    printf '%s\\n' 'first diagnostic line' >&2\n"
        "    printf '%s\\n' 'https://operator:supersecret@index.invalid/simple?token=abc123' >&2\n"
        "    printf '%s\\n' 'Because native-demo==1.0.0 has no usable wheels and building from source is disabled' >&2\n"
        "    exit 1 ;;\n"
        "esac\n",
    )
    result = _install_result(tmp_path / "home")

    applied = script_runtime.perform_apply_install("posix", result, uv_bin=str(uv_bin))

    assert applied["ok"] is False
    assert applied["status"] == "partial_failure"
    assert applied["error_code"] == "LOCKED_WHEEL_UNAVAILABLE"
    assert applied["failed_step"] == "application_sync"
    assert applied["dependency_package"] == "native-demo==1.0.0"
    assert applied["target_platform"] == "linux_x86_64_cp313"
    assert applied["python_version"] == "3.13"
    assert applied["runtime_info"]["application_runtime_ready"] is False
    assert applied["runtime_info"]["full_tty_allowed"] is False
    assert applied["system_python_modified"] is False
    assert applied["runtime_info"]["admin_used"] is False
    assert applied["runtime_info"]["network_scan"] == "not_run"
    assert applied["runtime_info"]["console_probe"] == "not_run"
    assert applied["osc_writes_sent"] == 0
    assert "pre-built dependency wheel" in applied["message"].lower()
    assert "compiler" in applied["message"].lower()
    assert "build-essential" not in applied["message"].lower()
    assert "traceback" not in applied["message"].lower()

    diagnostic = Path(applied["diagnostic_log_path"])
    assert diagnostic.parent == tmp_path / "home" / ".m32-bridge" / "logs"
    assert stat.S_IMODE(diagnostic.stat().st_mode) == 0o600
    log_text = diagnostic.read_text(encoding="utf-8")
    assert "first diagnostic line" in log_text
    assert "native-demo==1.0.0" in log_text
    assert "FAKE_UV_ARGV" not in log_text
    assert "supersecret" not in log_text
    assert "abc123" not in log_text
    assert "[REDACTED]" in log_text

    script_runtime._print_plain("posix", applied, dry_run=False)
    terminal = capsys.readouterr().out
    assert "error_code: LOCKED_WHEEL_UNAVAILABLE" in terminal
    assert "failed_step: application_sync" in terminal
    assert "dependency_package: native-demo==1.0.0" in terminal
    assert f"diagnostic_log_path: {diagnostic}" in terminal
    assert "first diagnostic line" not in terminal


@pytest.mark.parametrize(
    ("stderr", "expected_code"),
    [
        ("dns error: failed to lookup address information", "DNS_RESOLUTION_FAILED"),
        ("request timed out while downloading", "DOWNLOAD_TIMEOUT"),
        ("TLS certificate verify failed", "TLS_CERTIFICATE_FAILED"),
        ("No space left on device", "DISK_SPACE_INSUFFICIENT"),
        ("Permission denied", "PERMISSION_DENIED"),
        ("unexpected resolver failure", "APPLICATION_SYNC_FAILED"),
    ],
)
def test_sync_failure_classification_does_not_guess(stderr: str, expected_code: str):
    classification = script_runtime.classify_install_failure(
        stderr,
        default_error_code="APPLICATION_SYNC_FAILED",
    )

    assert classification.error_code == expected_code
    if expected_code != "LOCKED_WHEEL_UNAVAILABLE":
        assert classification.dependency_package is None


def test_blocked_target_fails_before_subprocess_or_toolchain_attempt(monkeypatch, tmp_path):
    uv_bin = _fake_uv(tmp_path, "printf '%s\\n' 'must not run' >> \"$FORBIDDEN_CALL_LOG\"\n")
    forbidden_log = tmp_path / "forbidden.log"
    monkeypatch.setenv("FORBIDDEN_CALL_LOG", str(forbidden_log))
    result = _install_result(tmp_path / "home", platform="macos", architecture="x86_64")

    applied = script_runtime.perform_apply_install("posix", result, uv_bin=str(uv_bin))

    assert applied["error_code"] == "LOCKED_WHEEL_UNAVAILABLE"
    assert applied["dependency_package"] == "cryptography==49.0.0"
    assert applied["target_platform"] == "macos_x86_64_cp313"
    assert not forbidden_log.exists()


def test_generated_launchers_are_frozen_no_build_and_no_sync(tmp_path):
    posix_uv = _fake_uv(tmp_path / "posix-tools", "exit 0\n")
    posix_app = tmp_path / "home" / ".m32-bridge" / "app"
    posix_launcher = tmp_path / "home" / ".local" / "bin" / "m32-bridge"
    script_runtime._apply_user_local_install(
        "posix",
        {"app_path": str(posix_app), "launcher_path": str(posix_launcher), "install_root": str(posix_app.parent)},
        uv_bin=str(posix_uv),
    )
    windows_uv = tmp_path / "Runtime" / "uv.exe"
    windows_uv.parent.mkdir()
    windows_uv.write_bytes(b"fake")
    windows_app = tmp_path / "LocalAppData" / "M32Bridge" / "app"
    windows_launcher = tmp_path / "LocalAppData" / "M32Bridge" / "bin" / "m32-bridge.cmd"
    script_runtime._apply_user_local_install(
        "windows",
        {"app_path": str(windows_app), "launcher_path": str(windows_launcher), "install_root": str(windows_app.parent)},
        uv_bin=str(windows_uv),
    )

    posix = posix_launcher.read_text(encoding="utf-8")
    windows = windows_launcher.read_text(encoding="utf-8")
    assert '"$UV_BIN" run --frozen --managed-python --python 3.13 --no-build --no-sync' in posix
    assert '"%UV_BIN%" run --frozen --managed-python --python 3.13 --no-build --no-sync' in windows
