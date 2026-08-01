from __future__ import annotations

import argparse
import json
import os
import platform as py_platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .planner import plan_dry_run_install
from .runtime_manager import (
    APPROVED_PYTHON_MINOR,
    PROJECT_PYTHON_RANGE,
    RuntimeManagerState,
    detect_uv_status,
    inspect_runtime,
    managed_python_policy,
    platform_information,
)
VERSION = "0.1.0"
IDEMPOTENCY_STATES = (
    "fresh_install",
    "existing_install",
    "repair",
    "update",
    "already_current",
    "partial_failure",
    "failed",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M32 Bridge user-local installer runtime")
    parser.add_argument("--surface", choices=("posix", "windows"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--platform", choices=("macos", "linux", "wsl", "raspberry_pi_os", "windows_powershell", "windows_cmd"))
    parser.add_argument("--current-version")
    parser.add_argument("--target-version", default=VERSION)
    parser.add_argument("--install-source", choices=("local_checkout", "github_raw", "github_release_or_archive"), default=os.environ.get("M32_INSTALL_SOURCE_KIND", "local_checkout"))
    parser.add_argument("--source-url", default=os.environ.get("M32_INSTALL_SOURCE_URL"))
    parser.add_argument("--source-ref", default=os.environ.get("M32_INSTALL_SOURCE_REF"))
    parser.add_argument("--confirm-dependency-actions", action="store_true")
    parser.add_argument("--bootstrap-apply", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--uv-bin", default=os.environ.get("M32_INSTALL_UV_BIN"), help=argparse.SUPPRESS)
    parser.add_argument("--tty", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--color", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    result = build_install_result(
        surface=args.surface,
        platform=args.platform,
        dry_run=args.dry_run,
        json_output=args.json_output,
        confirmed_dependency_actions=args.confirm_dependency_actions,
        home=os.environ.get("HOME"),
        local_app_data=os.environ.get("LOCALAPPDATA"),
        current_version=args.current_version,
        target_version=args.target_version,
        install_source=args.install_source,
        source_url=args.source_url,
        source_ref=args.source_ref,
    )
    tty_mode = bool(args.tty or (sys.stdin.isatty() and sys.stdout.isatty() and not args.json_output))
    if not args.dry_run:
        if not result["installer_can_continue"]:
            if args.json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            elif tty_mode:
                _print_plain(args.surface, result, dry_run=args.dry_run)
            else:
                _print_plain(args.surface, result, dry_run=args.dry_run, tty=tty_mode, color=args.color)
            return 1
        result = perform_apply_install(
            args.surface,
            result,
            bootstrap_apply=args.bootstrap_apply,
            uv_bin=args.uv_bin,
        )

    if args.json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif tty_mode and result.get("runtime_info", {}).get("application_runtime_ready"):
        _run_tty_app(args.surface, result, dry_run=args.dry_run, color=args.color)
    else:
        _print_plain(args.surface, result, dry_run=args.dry_run)
    return 0 if result["ok"] else 1


def perform_apply_install(
    surface: str,
    result: dict[str, Any],
    *,
    bootstrap_apply: bool = False,
    uv_bin: str | None = None,
) -> dict[str, Any]:
    bootstrap_apply = bool(bootstrap_apply or result.get("bootstrap_apply"))
    uv_bin = uv_bin or result.get("uv_bin") or os.environ.get("M32_INSTALL_UV_BIN")
    try:
        resolved_uv_bin = _resolve_uv_executable(surface, uv_bin)
        _apply_user_local_install(surface, result, uv_bin=resolved_uv_bin)
        runtime_readiness = (
            _synchronize_application_runtime(surface, result, uv_bin=resolved_uv_bin)
            if bootstrap_apply
            else {
                "ready": True,
                "managed_python_version": result.get("runtime_info", {}).get("managed_python_version") or "3.13.x",
                "required_imports": "not_run_internal_call",
            }
        )
        if not runtime_readiness.get("ready"):
            raise InstallStepError(
                error_code="APPLICATION_RUNTIME_NOT_READY",
                failed_step="application_runtime_readiness",
                message=str(runtime_readiness.get("message") or "Required application imports did not pass."),
                recovery_action="Rerun the installer to repair the user-local application environment.",
            )
    except OSError as exc:
        return _controlled_install_failure(
            surface,
            result,
            error_code="APP_MATERIALIZATION_FAILED",
            failed_step="application_install",
            message=f"Application files could not be installed: {exc}",
            recovery_action="Rerun the installer to repair the user-local application files.",
            partial=True,
        )
    except ValueError as exc:
        return _controlled_install_failure(
            surface,
            result,
            error_code="INSTALL_BOUNDARY_REJECTED",
            failed_step="install_boundary",
            message=str(exc),
            recovery_action="Review the user-local target paths and rerun the installer.",
        )
    except InstallStepError as exc:
        return _controlled_install_failure(
            surface,
            result,
            error_code=exc.error_code,
            failed_step=exc.failed_step,
            message=exc.message,
            recovery_action=exc.recovery_action,
            partial=True,
        )

    status = "already_current" if result["status"] in {"fresh_install", "repair", "update"} else result["status"]
    mcp_guidance, lifecycle_guidance = _post_install_guidance(surface, result, status=status)
    public_result = _without_private_fields(result)
    runtime_info = {
        **dict(public_result.get("runtime_info") or {}),
        "application_runtime_ready": True,
        "full_tty_allowed": True,
        "managed_python_version": runtime_readiness.get("managed_python_version", "3.13.x"),
        "required_imports": runtime_readiness.get("required_imports", "ok"),
        "admin_used": False,
        "network_scan": "not_run",
        "console_probe": "not_run",
    }
    return {
        **public_result,
        "ok": True,
        "status": status,
        "path_updated": False,
        "runtime_info": runtime_info,
        "first_run_setup": {
            "offered": True,
            "interactive": False,
            "attempted_path": "not_attempted",
            "classification": None,
            "osc_writes_sent": 0,
            "hardware_verified": False,
        },
        "verification_guidance": {
            "offered": True,
            "commands": [
                "m32-bridge health",
                "m32-bridge setup",
                "m32-bridge get-info",
                "m32-bridge detect-device",
                "m32-bridge doctor-runtime",
            ],
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        },
        "mcp_guidance": mcp_guidance,
        "lifecycle_guidance": lifecycle_guidance,
        "message": _message({**result, "status": status}),
        "hardware_verified": False,
        "production_live_ready": False,
        "osc_writes_sent": 0,
    }


class InstallStepError(RuntimeError):
    def __init__(self, *, error_code: str, failed_step: str, message: str, recovery_action: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.failed_step = failed_step
        self.message = message
        self.recovery_action = recovery_action


def _resolve_uv_executable(surface: str, uv_bin: str | None) -> str:
    if not uv_bin:
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message="The absolute uv executable path is required before launcher creation.",
            recovery_action="Rerun the installer so it can pass the detected user-local uv path to the launcher.",
        )
    candidate = Path(uv_bin).expanduser()
    if not candidate.is_absolute() or not candidate.is_file():
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message=f"The uv executable path is unavailable or not absolute: {uv_bin}",
            recovery_action="Rerun the installer so it can verify the user-local uv executable before launcher creation.",
        )
    if surface != "windows" and not os.access(candidate, os.X_OK):
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message=f"The uv executable is not executable: {candidate}",
            recovery_action="Restore execute permission on the user-local uv binary, then rerun the installer.",
        )
    return str(candidate.resolve())


def _controlled_install_failure(
    surface: str,
    result: dict[str, Any],
    *,
    error_code: str,
    failed_step: str,
    message: str,
    recovery_action: str,
    partial: bool = False,
) -> dict[str, Any]:
    from .lifecycle import render_lifecycle_guidance

    status = "partial_failure" if partial else "failed"
    public_result = _without_private_fields(result)
    runtime_info = {
        **dict(public_result.get("runtime_info") or {}),
        "application_runtime_ready": False,
        "full_tty_allowed": False,
        "failed_step": failed_step,
        "recovery_action": recovery_action,
        "admin_used": False,
        "network_scan": "not_run",
        "console_probe": "not_run",
    }
    return {
        **public_result,
        "ok": False,
        "status": status,
        "error_code": error_code,
        "message": message,
        "installer_can_continue": False,
        "runtime_info": runtime_info,
        "system_python_modified": False,
        "lifecycle_guidance": render_lifecycle_guidance(surface=surface, install_status=status),
        "hardware_verified": False,
        "production_live_ready": False,
        "osc_writes_sent": 0,
    }


def _synchronize_application_runtime(surface: str, result: dict[str, Any], *, uv_bin: str | None = None) -> dict[str, Any]:
    uv_bin = Path(str(uv_bin or os.environ.get("M32_INSTALL_UV_BIN") or ""))
    if not str(uv_bin) or not uv_bin.is_file() or not os.access(uv_bin, os.X_OK):
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message="The user-local uv executable could not be used by the current installer process.",
            recovery_action="Rerun the installer; no shell restart or PATH export should be required.",
        )
    app_path = Path(result["app_path"])
    base = [str(uv_bin), "--directory", str(app_path)]
    env = dict(os.environ)
    env["UV_MANAGED_PYTHON"] = "1"
    sync = _run_install_command(
        [*base, "sync", "--frozen", "--managed-python", "--python", APPROVED_PYTHON_MINOR],
        env=env,
        error_code="APP_SYNC_FAILED",
        failed_step="application_sync",
        recovery_action="Rerun the installer to repair the frozen application environment.",
    )
    del sync
    smoke_code = "import yaml, mcp, pydantic, m32_bridge; print('READY')"
    smoke = _run_install_command(
        [*base, "run", "--frozen", "--managed-python", "--python", APPROVED_PYTHON_MINOR, "python", "-c", smoke_code],
        env=env,
        error_code="REQUIRED_IMPORT_SMOKE_FAILED",
        failed_step="required_import_smoke",
        recovery_action="Rerun the installer to restore application dependencies.",
    )
    version = _run_install_command(
        [*base, "run", "--frozen", "--managed-python", "--python", APPROVED_PYTHON_MINOR, "python", "-c", "import platform; print(platform.python_version())"],
        env=env,
        error_code="MANAGED_PYTHON_CHECK_FAILED",
        failed_step="managed_python_check",
        recovery_action="Rerun the installer to repair managed CPython 3.13.",
    )
    launcher = Path(result["launcher_path"])
    ready = app_path.is_dir() and (app_path / ".venv").is_dir() and launcher.is_file() and smoke.stdout.strip() == "READY"
    return {
        "ready": ready,
        "managed_python_version": version.stdout.strip(),
        "required_imports": "ok" if smoke.stdout.strip() == "READY" else "failed",
    }


def _without_private_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key not in {"bootstrap_apply", "uv_bin"}}


def _run_install_command(
    argv: list[str],
    *,
    env: dict[str, str],
    error_code: str,
    failed_step: str,
    recovery_action: str,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(argv, check=False, capture_output=True, text=True, env=env)
    except OSError as exc:
        raise InstallStepError(
            error_code=error_code,
            failed_step=failed_step,
            message=f"{failed_step} could not start: {exc}",
            recovery_action=recovery_action,
        ) from None
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "command failed").strip().splitlines()[-1]
        raise InstallStepError(
            error_code=error_code,
            failed_step=failed_step,
            message=f"{failed_step} failed: {detail}",
            recovery_action=recovery_action,
        )
    return completed


def _post_install_guidance(surface: str, result: dict[str, Any], *, status: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from .lifecycle import render_lifecycle_guidance
    from .mcp_guidance import render_mcp_guidance

    launcher_path = Path(str(result.get("launcher_path", "")))
    launcher_root = launcher_path.parents[2] if len(launcher_path.parents) >= 3 else None
    mcp_guidance = render_mcp_guidance(
        os_family="windows" if surface == "windows" else None,
        home=None if surface == "windows" else launcher_root,
        local_app_data=launcher_root if surface == "windows" else None,
    )
    return mcp_guidance, render_lifecycle_guidance(surface=surface, install_status=status)


def _run_tty_app(surface: str, result: dict[str, Any], *, dry_run: bool, color: bool) -> None:
    from .tty_app import run_tty_app

    run_tty_app(surface, result, dry_run=dry_run, color=color)


def installer_contact_text(*args: Any, **kwargs: Any) -> str:
    from .tty_app import installer_contact_text as render

    return render(*args, **kwargs)


def installer_help_text(*args: Any, **kwargs: Any) -> str:
    from .tty_app import installer_help_text as render

    return render(*args, **kwargs)


def render_tty_installer(*args: Any, **kwargs: Any) -> str:
    from .tty_app import render_tty_installer as render

    return render(*args, **kwargs)


def build_install_result(
    *,
    surface: str,
    platform: str | None = None,
    dry_run: bool = True,
    json_output: bool = False,
    confirmed_dependency_actions: bool = False,
    home: Path | str | None = None,
    local_app_data: Path | str | None = None,
    uv_state: RuntimeManagerState | None = None,
    current_version: str | None = None,
    target_version: str | None = None,
    install_source: str = "local_checkout",
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    surface_platform = platform or _detect_platform(surface)
    app_exists, launcher_exists = _detect_existing_state(surface, home=home, local_app_data=local_app_data)
    runtime = uv_state or _uv_state_from_environment()
    uv_detected = runtime.uv_status in {"present", "installed_user_local"}
    required_actions = [] if uv_detected else [_uv_required_action(surface, _dependency_target_root(surface, home, local_app_data))]

    result = plan_dry_run_install(
        platform=surface_platform,
        home=home or os.environ.get("HOME"),
        local_app_data=local_app_data or os.environ.get("LOCALAPPDATA"),
        uv_state=runtime,
        current_version=current_version,
        target_version=target_version or VERSION,
        app_exists=app_exists,
        launcher_exists=launcher_exists,
        partial_failure_marker=_partial_failure_marker(surface, home=home, local_app_data=local_app_data),
    )

    missing_uv = not uv_detected
    if missing_uv:
        result["status"] = "RUNTIME_SETUP_REQUIRED" if dry_run or json_output else "UV_MISSING"
        result["ok"] = False
        result["error_code"] = "RUNTIME_SETUP_REQUIRED" if dry_run or json_output else "UV_MISSING_CONFIRMATION_REQUIRED"
    if result.get("status") == "partial_failure":
        result["ok"] = False
        result["error_code"] = result.get("error_code") or "PARTIAL_FAILURE_RECOVERY_REQUIRED"
    result.update(
        {
            "dry_run": dry_run,
            "install_source": install_source,
            "source_url": source_url,
            "source_ref": source_ref or target_version or VERSION,
            "target_version": target_version or VERSION,
            "uv_required": True,
            "uv_detected": uv_detected,
            "python_required": True,
            "global_python_required": False,
            "python_managed_by_uv": True,
            "managed_python_policy": managed_python_policy(),
            "approved_python_minor": APPROVED_PYTHON_MINOR,
            "project_python_range": PROJECT_PYTHON_RANGE,
            "runtime_info": inspect_runtime(),
            "platform_info": platform_information(),
            "system_python_modified": False,
            "global_python_installed": False,
            "default_python_aliases_installed": False,
            "installer_can_continue": uv_detected and (not required_actions or confirmed_dependency_actions),
            "confirmation_required": bool(required_actions),
            "required_actions": required_actions,
        }
    )
    result["lifecycle_guidance"] = _lifecycle_guidance(surface, result)
    result["message"] = _message(result)
    result["recommendations"] = _recommendations(surface, result)
    _assert_user_local_result(surface, result)
    return result


def _lifecycle_guidance(surface: str, result: dict[str, Any]) -> dict[str, Any]:
    from .lifecycle import render_lifecycle_guidance

    return render_lifecycle_guidance(
        surface=surface,
        install_status=str(result.get("status") or "already_current"),
        app_path=result.get("app_path"),
        launcher_path=result.get("launcher_path"),
    )


def _detect_platform(surface: str) -> str:
    if surface == "windows":
        return "windows_powershell"
    if _is_wsl():
        return "wsl"
    system = py_platform.system().lower()
    if system == "darwin":
        return "macos"
    if _is_raspberry_pi_os():
        return "raspberry_pi_os"
    return "linux"


def _is_wsl() -> bool:
    text = ""
    try:
        text = Path("/proc/version").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        pass
    return "microsoft" in text.lower() or "WSL_DISTRO_NAME" in os.environ


def _is_raspberry_pi_os() -> bool:
    try:
        os_release = Path("/etc/os-release").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        os_release = ""
    return "raspbian" in os_release or "raspberry pi os" in os_release


def _uv_state_from_environment() -> RuntimeManagerState:
    if os.environ.get("M32_INSTALL_UV_BLOCKED") == "1":
        return RuntimeManagerState(
            uv_status="blocked",
            manual_guidance="uv setup is blocked. Install uv in user space, then rerun the installer.",
            error="UV_BLOCKED",
        )
    # Test-only override; production detection comes from the actual PATH.
    if os.environ.get("M32_INSTALL_ASSUME_UV") == "installed_user_local":
        return RuntimeManagerState(uv_status="installed_user_local")
    return detect_uv_status(allow_user_install=False)


def _detect_existing_state(surface: str, *, home: Path | str | None = None, local_app_data: Path | str | None = None) -> tuple[bool, bool]:
    if surface == "windows":
        base = Path(local_app_data or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        app = base / "M32Bridge" / "app"
        launcher = base / "M32Bridge" / "bin" / "m32-bridge.cmd"
    else:
        home_path = Path(home or os.environ.get("HOME") or Path.home())
        app = home_path / ".m32-bridge" / "app"
        launcher = home_path / ".local" / "bin" / "m32-bridge"
    return app.exists(), launcher.exists()


def _partial_failure_marker(surface: str, *, home: Path | str | None = None, local_app_data: Path | str | None = None) -> bool:
    if surface == "windows":
        base = Path(local_app_data or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (base / "M32Bridge" / ".partial_failure").exists()
    home_path = Path(home or os.environ.get("HOME") or Path.home())
    return (home_path / ".m32-bridge" / ".partial_failure").exists()


def _apply_user_local_install(surface: str, result: dict[str, Any], *, uv_bin: str) -> None:
    _assert_user_local_result(surface, result)
    resolved_uv_bin = _resolve_uv_executable(surface, uv_bin)
    app_path = Path(result["app_path"])
    launcher_path = Path(result["launcher_path"])
    _materialize_app(app_path)
    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    if surface == "windows":
        app_value = _cmd_assignment_value(str(app_path))
        uv_value = _cmd_assignment_value(resolved_uv_bin)
        launcher_path.write_text(
            "@echo off\r\n"
            f"set \"M32_BRIDGE_APP_DIR={app_value}\"\r\n"
            f"set \"UV_BIN={uv_value}\"\r\n"
            "set \"PYTHONPATH=%M32_BRIDGE_APP_DIR%\\src;%PYTHONPATH%\"\r\n"
            "set \"UV_MANAGED_PYTHON=1\"\r\n"
            "cd /d \"%M32_BRIDGE_APP_DIR%\"\r\n"
            "\"%UV_BIN%\" run --frozen --managed-python --python 3.13 --project \"%M32_BRIDGE_APP_DIR%\" python -m m32_bridge.__main__ %*\r\n",
            encoding="utf-8",
        )
    else:
        launcher_path.write_text(
            "#!/bin/sh\n"
            f"APP_DIR={shlex.quote(str(app_path))}\n"
            f"UV_BIN={shlex.quote(resolved_uv_bin)}\n"
            "cd \"$APP_DIR\"\n"
            "PYTHONPATH=\"$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}\"\n"
            "UV_MANAGED_PYTHON=1\n"
            "export M32_BRIDGE_APP_DIR=\"$APP_DIR\" PYTHONPATH UV_MANAGED_PYTHON\n"
            "exec \"$UV_BIN\" run --frozen --managed-python --python 3.13 --project \"$APP_DIR\" python -m m32_bridge.__main__ \"$@\"\n",
            encoding="utf-8",
        )
        launcher_path.chmod(0o755)


def _cmd_assignment_value(value: str) -> str:
    if any(character in value for character in ('"', "\r", "\n")):
        raise ValueError("Windows launcher path contains an unsupported character")
    return value.replace("%", "%%")


def _materialize_app(app_path: Path, *, source_root: Path | None = None) -> None:
    source = source_root or _repo_root()
    _assert_materialization_source(source)
    app_path.mkdir(parents=True, exist_ok=True)
    for filename in ("pyproject.toml", "uv.lock", ".python-version", "README.md"):
        src = source / filename
        if src.is_file():
            shutil.copy2(src, app_path / filename)
    _copy_tree_filtered(source / "src", app_path / "src")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _assert_materialization_source(source: Path) -> None:
    required = [source / "pyproject.toml", source / "uv.lock", source / "src" / "m32_bridge"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise OSError(f"materialization source missing required files: {', '.join(missing)}")


def _copy_tree_filtered(source: Path, destination: Path) -> None:
    if not source.exists():
        raise OSError(f"required source tree missing: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if _should_skip_materialized_path(child):
            continue
        target = destination / child.name
        if child.is_dir():
            _copy_tree_filtered(child, target)
        elif child.is_file():
            shutil.copy2(child, target)


def _should_skip_materialized_path(path: Path) -> bool:
    name = path.name
    if name in {
        ".git",
        ".venv",
        ".pytest_cache",
        ".DS_Store",
        "__pycache__",
        "tests",
        ".env",
        ".env.local",
        "config.local.yaml",
        "config.yaml",
    }:
        return True
    if name.endswith((".pyc", ".pyo")):
        return True
    return False


def _dependency_target_root(surface: str, home: Path | str | None, local_app_data: Path | str | None) -> Path:
    if surface == "windows":
        return Path(local_app_data or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return Path(home or os.environ.get("HOME") or Path.home())


def _uv_required_action(surface: str, target_root: Path) -> dict[str, Any]:
    if surface == "windows":
        command_preview = "Invoke-RestMethod downloads https://astral.sh/uv/install.ps1 to a temporary file; run only after exact INSTALL confirmation; then uv python install 3.13"
        target_paths = [str(target_root / "M32Bridge" / "runtime" / "uv")]
    else:
        command_preview = "curl downloads https://astral.sh/uv/install.sh to a temporary file (wget/manual fallback); run only after exact INSTALL confirmation; then uv python install 3.13"
        target_paths = [str(target_root / ".local" / "bin" / "uv")]
    return {
        "action_id": "INSTALL_UV_USER_LOCAL",
        "title": "Install uv in user space",
        "reason": "M32 Bridge uses uv-managed CPython 3.13 without changing system Python or installing default aliases.",
        "command_preview": command_preview,
        "requires_confirmation": True,
        "risk_level": "user_local",
        "target_paths": target_paths,
        "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
        "user_can_skip": False,
    }


def _assert_user_local_result(surface: str, result: dict[str, Any]) -> None:
    paths = [Path(result["app_path"]), Path(result["launcher_path"]), Path(result.get("install_root") or result["app_path"])]
    for action in result.get("required_actions") or []:
        for target in action.get("target_paths", []):
            paths.append(Path(target))
        preview = action.get("command_preview", "").lower()
        forbidden_preview = ["sudo", "runas", "start-process -verb runas", "rm -rf", "del /", "rmdir /s", "format "]
        if any(token in preview for token in forbidden_preview):
            raise ValueError("dependency action contains forbidden admin or destructive command")
    for path in paths:
        if _is_system_path(surface, path):
            raise ValueError(f"system path rejected for user-local installer boundary: {path}")


def _is_system_path(surface: str, path: Path) -> bool:
    text = str(path)
    lower = text.lower().replace("\\", "/")
    if surface == "windows":
        return lower.startswith("c:/windows") or lower.startswith("c:/program files")
    return text in {"/", "/usr", "/usr/local", "/opt", "/etc", "/bin", "/sbin", "/var"} or lower.startswith(
        ("/usr/", "/usr/local/", "/opt/", "/etc/", "/bin/", "/sbin/")
    )


def _message(result: dict[str, Any]) -> str:
    state = result["status"]
    if state == "fresh_install":
        return "fresh_install planned for user-local app and launcher paths."
    if state == "existing_install":
        return "existing_install detected; inspect user-local files before changing them."
    if state == "repair":
        return "repair planned; restore missing user-local launcher without deleting saved config."
    if state == "update":
        return "update planned; preserve saved config unless the user changes it later."
    if state == "already_current":
        return "already_current; run m32-bridge health in a new terminal if PATH changed."
    if state == "partial_failure":
        return "partial_failure detected; use recovery guidance before reporting success."
    if state == "failed":
        return "failed; no silent success was reported."
    if state == "UV_MISSING":
        return "UV_MISSING: uv is required before install can continue; confirm guided action explicitly."
    if state == "RUNTIME_SETUP_REQUIRED":
        return "RUNTIME_SETUP_REQUIRED: uv is missing; review required_actions before applying install."
    return "installer status is available."


def _recommendations(surface: str, result: dict[str, Any]) -> list[str]:
    common = [
        "Run m32-bridge health after install.",
        "Post-install verification commands: m32-bridge health, m32-bridge setup, m32-bridge get-info, m32-bridge detect-device, m32-bridge doctor-runtime.",
        "Run m32-bridge setup later for console endpoint setup.",
        "TTY installer output uses DXBMARK styled sections; JSON stays machine-readable.",
        "No /set, OSC writes, hardware verification, or production/live readiness is performed by install evidence.",
        "Manual-copy MCP guidance: use m32-bridge mcp-server as a local stdio command; no Claude, ChatGPT, Gemini, Antigravity, Codex, VS Code, or Cursor config is written automatically.",
        "Lifecycle guidance covers update, repair, and uninstall for user-local app and launcher paths; retain saved config by default.",
    ]
    if surface == "windows":
        common.append("Use PowerShell irm / Invoke-RestMethod guidance; CMD usage is through m32-bridge.cmd after install.")
    else:
        common.append("Download with curl when available, wget fallback, or manual download; inspect before running.")
    if result.get("uv_status") == "manual_action_required":
        common.append("uv requires user-local setup guidance; global py is not required and confirmation is required.")
    if result.get("status") == "partial_failure":
        common.append("Recovery: repair the user-local app and launcher, or remove incomplete user-local files.")
    return common


def _print_plain(surface: str, result: dict[str, Any], *, dry_run: bool, tty: bool = False, color: bool = False) -> None:
    if tty:
        from .tty_app import render_tty_installer

        print(render_tty_installer(surface, result, dry_run=dry_run, color=color))
        return
    print("M32 Bridge installer status")
    print(f"surface: {surface}")
    print(f"mode: {'dry-run' if dry_run else 'apply'}")
    print(f"status: {result['status']}")
    print(f"version: {result.get('version', VERSION)}")
    print(f"install_source: {result.get('install_source', 'local_checkout')}")
    print(f"install_root: {result.get('install_root')}")
    print(f"app_path: {result['app_path']}")
    print(f"launcher_path: {result['launcher_path']}")
    print("user_local: true")
    print("admin_required=false")
    print("requires_admin=false")
    print("global_py_required=false")
    print("hardware_verified=false")
    print("production_live_ready=false")
    print("osc_writes_sent=0")
    lifecycle = result.get("lifecycle_guidance") or {}
    if lifecycle:
        print("lifecycle_guidance: update repair uninstall")
        print(f"config_path: {lifecycle.get('config_path')}")
        print("config_handling: retain saved config by default; remove only after explicit confirmation")
    print(f"message: {result.get('message')}")
    for recommendation in result.get("recommendations", []):
        print(f"- {recommendation}")


if __name__ == "__main__":
    raise SystemExit(main())
