from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence


UvStatus = Literal["present", "installed_user_local", "blocked", "manual_action_required"]

APPROVED_PYTHON_MINOR = "3.13"
PROJECT_PYTHON_RANGE = ">=3.11,<3.14"
MANAGED_PYTHON_POLICY: dict[str, Any] = {
    "implementation": "CPython",
    "preferred_minor": APPROVED_PYTHON_MINOR,
    "allowed_range": PROJECT_PYTHON_RANGE,
    "installation_type": "uv_managed_user_local",
    "system_python_modified": False,
    "global_python_installed": False,
    "default_python_aliases_installed": False,
    "admin_required": False,
}
UV_BOOTSTRAP_USER_AGENT = "X32-Bridge-MCP-Installer"
UV_INSTALL_URLS = {
    "posix": "https://astral.sh/uv/install.sh",
    "windows": "https://astral.sh/uv/install.ps1",
}
OFFICIAL_SOURCE_ARCHIVE_URLS = {
    "posix": "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz",
    "windows": "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.zip",
}
OFFICIAL_RAW_INSTALLER_URLS = {
    "posix": "https://raw.githubusercontent.com/DXBMARK/m32-bridge/main/scripts/install.sh",
    "windows": "https://raw.githubusercontent.com/DXBMARK/m32-bridge/main/scripts/install.ps1",
}


@dataclass(frozen=True)
class RuntimeManagerState:
    uv_status: UvStatus
    global_py_required: bool = False
    manual_guidance: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.uv_status in {"present", "installed_user_local"}


def detect_uv_status(
    *,
    allow_user_install: bool = False,
    uv_executable: str | None = None,
    environ: Mapping[str, str] | None = None,
    finder: Callable[[str], str | None] | None = None,
) -> RuntimeManagerState:
    env = dict(os.environ if environ is None else environ)
    find = finder or _finder_for_environ(env)
    if uv_executable or find("uv"):
        return RuntimeManagerState(uv_status="present")
    if allow_user_install:
        return RuntimeManagerState(
            uv_status="manual_action_required",
            manual_guidance="Install uv in user space, then rerun the installer.",
        )
    return RuntimeManagerState(
        uv_status="manual_action_required",
        manual_guidance="uv is required. Install uv manually or use an approved user-local install path.",
    )


def managed_python_policy() -> dict[str, Any]:
    return dict(MANAGED_PYTHON_POLICY)


def download_capability(
    *,
    surface: str,
    finder: Callable[[str], str | None] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(os.environ if environ is None else environ)
    find = finder or _finder_for_environ(env)
    if surface == "windows":
        return {
            "primary_tool": "PowerShell Invoke-WebRequest/Invoke-RestMethod available",
            "wget_fallback": "optional, not installed",
            "manual_fallback": "available",
        }
    curl_path = find("curl")
    wget_path = find("wget")
    if curl_path:
        primary = "curl available"
        wget_fallback = "available" if wget_path else "optional, not installed"
    elif wget_path:
        primary = "wget available"
        wget_fallback = "primary available"
    else:
        primary = "not available"
        wget_fallback = "optional, not installed"
    return {
        "primary_tool": primary,
        "wget_fallback": wget_fallback,
        "manual_fallback": "available",
    }


def inspect_runtime(
    *,
    environ: Mapping[str, str] | None = None,
    finder: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    find = finder or _finder_for_environ(env)
    uv_path = find("uv")
    uv_version: str | None = None
    managed_path: str | None = None
    managed_version: str | None = None
    if uv_path:
        uv_version, _ = _run_capture([uv_path, "--version"], environ=env)
        found, returncode = _run_capture(
            [uv_path, "python", "find", "--managed-python", APPROVED_PYTHON_MINOR],
            environ={**env, "UV_MANAGED_PYTHON": "1"},
        )
        if returncode == 0 and found.strip():
            candidate = found.strip().splitlines()[-1]
            version_text, version_rc = _run_capture([candidate, "--version"], environ=env)
            if version_rc == 0 and version_text.startswith(f"Python {APPROVED_PYTHON_MINOR}."):
                managed_path = candidate
                managed_version = version_text.removeprefix("Python ").strip()
    system_path = find("python3") or find("python")
    system_version: str | None = None
    if system_path:
        version_text, version_rc = _run_capture([system_path, "--version"], environ=env)
        if version_rc == 0:
            system_version = version_text.removeprefix("Python ").strip()
    return {
        "policy": managed_python_policy(),
        "uv_detected": bool(uv_path),
        "uv_version": uv_version.strip() if uv_version else None,
        "uv_path": uv_path,
        "managed_python_detected": bool(managed_path),
        "python_version": managed_version,
        "python_path": managed_path,
        "python_source": "uv_managed" if managed_path else "not_detected",
        "system_python_path": system_path,
        "system_python_version": system_version,
        "system_python_used": False,
        "approved_minor": APPROVED_PYTHON_MINOR,
        "project_required_range": PROJECT_PYTHON_RANGE,
        "launcher": "uv run --frozen --managed-python --python 3.13 --no-build --no-sync",
        "system_python_modified": False,
        "global_python_installed": False,
        "default_python_aliases_installed": False,
        "admin_required": False,
    }


def local_runtime_diagnostics(
    *,
    environ: Mapping[str, str] | None = None,
    app_path: str | None = None,
    launcher_path: str | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    runtime = inspect_runtime(environ=env)
    app = Path(app_path).expanduser() if app_path else None
    launcher = Path(launcher_path).expanduser() if launcher_path else None
    runtime.update(
        {
            "status": "ok" if runtime["uv_detected"] and runtime["managed_python_detected"] else "action_required",
            "app_files": "available" if app and app.exists() else "not_found",
            "launcher_file": "available" if launcher and launcher.exists() else "not_found",
            "launcher_executable": bool(launcher and launcher.exists() and os.access(launcher, os.X_OK)),
            "path_visibility": bool(launcher and str(launcher.parent) in env.get("PATH", "").split(os.pathsep)),
            "console_probe": "not_run",
            "network_scan": "not_run",
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }
    )
    return runtime


def platform_information(
    *,
    system: str | None = None,
    release: str | None = None,
    machine: str | None = None,
    environ: Mapping[str, str] | None = None,
    os_release_path: Path = Path("/etc/os-release"),
    proc_version_text: str | None = None,
    container_hint: str | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    system_name = system or platform.system()
    release_text = release or platform.release()
    architecture = machine or platform.machine() or "unknown"
    shell = Path(env.get("SHELL", "")).name or ("powershell" if env.get("PSModulePath") else "unknown")
    base: dict[str, Any] = {
        "os": system_name or "unknown",
        "version": platform.version() or "unknown",
        "kernel_build": release_text or "unknown",
        "architecture": architecture,
        "shell": shell,
        "wsl": "not_applicable",
        "container_hint": container_hint or _container_hint(),
    }
    lowered = system_name.lower()
    if lowered == "darwin":
        base["os"] = "macOS"
        base["version"] = platform.mac_ver()[0] or base["version"]
        base["kernel_build"] = f"Darwin {release_text}"
    elif lowered == "linux":
        release_fields = _read_os_release(os_release_path)
        base["os"] = release_fields.get("PRETTY_NAME") or "Linux"
        base["version"] = release_fields.get("VERSION_ID") or "unknown"
        text = proc_version_text
        if text is None:
            try:
                text = Path("/proc/version").read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
        base["wsl"] = "detected" if env.get("WSL_DISTRO_NAME") or "microsoft" in text.lower() else "not_detected"
    elif lowered == "windows":
        base["os"] = platform.platform() or "Windows"
        base["version"] = platform.version() or release_text or "unknown"
        base["kernel_build"] = platform.win32_ver()[1] or release_text or "unknown"
        base["powershell_version"] = env.get("M32_POWERSHELL_VERSION") or "not_checked"
        base["terminal_capability"] = "interactive" if sys.stdin.isatty() and sys.stdout.isatty() else "non_interactive"
    return base


def bootstrap_uv_and_python(
    *,
    surface: str,
    confirmation: str,
    input_url: str | None = None,
    downloader: Callable[[str, Path], None] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    finder: Callable[[str], str | None] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the fixed, allowlisted uv bootstrap. No caller-supplied command is executed."""
    if confirmation != "INSTALL":
        return {"ok": False, "status": "confirmation_required", "installed": False}
    if surface not in UV_INSTALL_URLS:
        return {"ok": False, "status": "unsupported_platform", "installed": False}
    url = input_url or UV_INSTALL_URLS[surface]
    if url != UV_INSTALL_URLS[surface]:
        return {"ok": False, "status": "unapproved_source", "installed": False}
    suffix = ".ps1" if surface == "windows" else ".sh"
    fd, temporary_name = tempfile.mkstemp(prefix="m32-uv-installer-", suffix=suffix)
    os.close(fd)
    temporary_path = Path(temporary_name)
    env = dict(os.environ if environ is None else environ)
    find = finder or _finder_for_environ(env)
    try:
        (downloader or _download_to_file)(url, temporary_path)
        if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            raise OSError("Downloaded uv installer is empty.")
        argv = (
            [
                _powershell_executable(find),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(temporary_path),
            ]
            if surface == "windows"
            else ["/bin/sh", str(temporary_path)]
        )
        completed = runner(argv, check=False, capture_output=True, text=True, env=env)
        if completed.returncode != 0:
            return {
                "ok": False,
                "status": "uv_install_failed",
                "installed": False,
                "error": (completed.stderr or completed.stdout).strip()[-500:],
            }
        uv_path = _rediscover_uv(find, env)
        if not uv_path:
            return {"ok": False, "status": "uv_redetection_failed", "installed": False}
        uv_version, uv_rc = _run_capture([uv_path, "--version"], environ=env)
        if uv_rc != 0:
            return {"ok": False, "status": "uv_version_failed", "installed": False}
        python_install = runner(
            [uv_path, "python", "install", APPROVED_PYTHON_MINOR],
            check=False,
            capture_output=True,
            text=True,
            env={**env, "UV_MANAGED_PYTHON": "1"},
        )
        if python_install.returncode != 0:
            return {
                "ok": False,
                "status": "managed_python_install_failed",
                "installed": False,
                "uv_path": uv_path,
                "uv_version": uv_version.strip(),
                "error": (python_install.stderr or python_install.stdout).strip()[-500:],
            }
        runtime = inspect_runtime(environ={**env, "UV_MANAGED_PYTHON": "1"}, finder=lambda name: uv_path if name == "uv" else find(name))
        return {
            "ok": bool(runtime["managed_python_detected"]),
            "status": "runtime_ready" if runtime["managed_python_detected"] else "managed_python_redetection_failed",
            "installed": bool(runtime["managed_python_detected"]),
            **runtime,
        }
    except (OSError, urllib.error.URLError) as exc:
        return {"ok": False, "status": "download_or_install_failed", "installed": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        temporary_path.unlink(missing_ok=True)


def _download_to_file(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": UV_BOOTSTRAP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        status = getattr(response, "status", 200)
        if status < 200 or status >= 300:
            raise OSError(f"HTTP status {status}")
        with target.open("wb") as output:
            shutil.copyfileobj(response, output)


def _run_capture(argv: Sequence[str], *, environ: Mapping[str, str] | None = None) -> tuple[str, int]:
    try:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            env=dict(os.environ if environ is None else environ),
        )
    except OSError:
        return "", 1
    return (completed.stdout or completed.stderr).strip(), completed.returncode


def which(name: str) -> str | None:
    """Compatibility wrapper for tests and callers that monkeypatch executable discovery."""
    return shutil.which(name)


def _finder_for_environ(environ: Mapping[str, str]) -> Callable[[str], str | None]:
    if environ.get("PATH") != os.environ.get("PATH"):
        return lambda name: _which(name, environ)
    return which


def _which(name: str, environ: Mapping[str, str]) -> str | None:
    return shutil.which(name, path=environ.get("PATH"))


def _rediscover_uv(finder: Callable[[str], str | None], environ: Mapping[str, str]) -> str | None:
    detected = finder("uv")
    if detected:
        return detected
    user_profile = Path(environ.get("USERPROFILE") or environ.get("HOME") or Path.home())
    candidates = (
        user_profile / ".local" / "bin" / "uv.exe",
        user_profile / ".local" / "bin" / "uv",
        user_profile / ".cargo" / "bin" / "uv.exe",
        user_profile / ".cargo" / "bin" / "uv",
    )
    return next((str(candidate) for candidate in candidates if candidate.is_file()), None)


def _powershell_executable(finder: Callable[[str], str | None]) -> str:
    return finder("pwsh") or finder("powershell") or "powershell"


def _read_os_release(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip("\"'")
    return values


def _container_hint() -> str:
    if Path("/.dockerenv").exists():
        return "possible_container"
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return "not_detected"
    return "possible_container" if any(token in cgroup for token in ("docker", "containerd", "kubepods", "podman")) else "not_detected"
