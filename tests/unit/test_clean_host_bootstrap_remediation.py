from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tarfile
import time

from m32_bridge.installer.runtime_manager import RuntimeManagerState


ROOT = Path(__file__).resolve().parents[2]
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"


def test_script_runtime_import_is_stdlib_safe_when_yaml_is_blocked():
    code = r"""
import builtins
import json
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "yaml" or name.startswith("yaml."):
        raise AssertionError("yaml imported during bootstrap")
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
import m32_bridge.installer.script_runtime
print(json.dumps({"ok": True, "yaml_loaded": "yaml" in __import__("sys").modules}))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True, "yaml_loaded": False}


def test_runtime_path_helpers_import_without_yaml_and_yaml_use_is_controlled():
    code = r"""
import builtins
import json
from pathlib import Path
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "yaml" or name.startswith("yaml."):
        raise ModuleNotFoundError("No module named 'yaml'")
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from m32_bridge.config.runtime import default_user_config_path, save_runtime_config
error = None
try:
    save_runtime_config(path=Path("unused.yaml"), host="127.0.0.1", port=10023, intended_target_type="unknown")
except RuntimeError as exc:
    error = str(exc)
print(json.dumps({"path": str(default_user_config_path()), "error": error}))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["path"].endswith("/.m32-bridge/runtime.yaml")
    assert "PyYAML" in payload["error"]
    assert "Traceback" not in completed.stderr


def test_apply_does_not_import_mcp_guidance_before_application_readiness(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    imported: list[str] = []
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if "mcp_guidance" in name:
            imported.append(name)
            raise AssertionError("mcp guidance imported before runtime readiness")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("copy failed")))
    uv_bin = tmp_path / ".local" / "bin" / "uv"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)

    applied = script_runtime.perform_apply_install("posix", result, uv_bin=str(uv_bin))

    assert applied["ok"] is False
    assert applied["runtime_info"]["failed_step"] == "application_install"
    assert imported == []
    assert "Traceback" not in applied["message"]


def test_bootstrap_scripts_use_absolute_uv_and_do_not_advertise_quick_actions():
    posix = POSIX_INSTALLER.read_text(encoding="utf-8")
    windows = WINDOWS_INSTALLER.read_text(encoding="utf-8")

    assert 'UV_BIN="${HOME}/.local/bin/uv"' in posix
    assert '"${UV_BIN}" --version' in posix
    assert 'M32_INSTALL_UV_BIN="${UV_BIN}"' in posix
    assert "Open a new terminal or add the reported user-local path" not in posix
    assert "Quick Actions" not in posix
    assert "After installation" in posix
    assert "These commands become available after the managed application runtime is installed." in posix

    assert "$script:UvBin" in windows
    assert "M32_INSTALL_UV_BIN" in windows
    assert "Quick Actions" not in windows
    assert "After installation" in windows


def test_help_separates_bootstrap_and_post_install_commands():
    posix = POSIX_INSTALLER.read_text(encoding="utf-8")
    windows = WINDOWS_INSTALLER.read_text(encoding="utf-8")

    for text in (posix, windows):
        assert "Bootstrap commands:" in text
        assert "/status /help /contact /clear /exit" in text
        assert "After installation:" in text
        assert "/health /setup /get-info /verify-device /doctor-runtime /mcp-config" in text
        assert "Installer commands:" not in text


def test_limited_terminal_bootstrap_has_no_truecolor_background_fill():
    text = POSIX_INSTALLER.read_text(encoding="utf-8")

    assert "terminal_color_mode" in text
    assert '"${TERM:-dumb}" = "dumb"' in text
    assert "COLORTERM" in text
    assert "48;2;36;57;71" in text
    assert "case \"$(terminal_color_mode)\"" in text


def test_apply_readiness_gate_controls_full_tty_and_keeps_safety_flags(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        script_runtime,
        "_synchronize_application_runtime",
        lambda *_args, **_kwargs: {
            "ready": True,
            "managed_python_version": "3.13.14",
            "required_imports": "ok",
        },
    )
    monkeypatch.setattr(script_runtime, "_post_install_guidance", lambda *_args, **_kwargs: ({"manual_copy_only": True}, {}))
    result["bootstrap_apply"] = True
    uv_bin = tmp_path / ".local" / "bin" / "uv"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)
    result["uv_bin"] = str(uv_bin)

    applied = script_runtime.perform_apply_install("posix", result)

    assert applied["runtime_info"]["application_runtime_ready"] is True
    assert applied["runtime_info"]["full_tty_allowed"] is True
    assert applied["runtime_info"]["managed_python_version"] == "3.13.14"
    assert applied["system_python_modified"] is False
    assert applied["runtime_info"]["admin_used"] is False
    assert applied["runtime_info"]["network_scan"] == "not_run"
    assert applied["runtime_info"]["console_probe"] == "not_run"
    assert applied["osc_writes_sent"] == 0


def test_subprocess_runtime_sync_uses_absolute_fake_uv_and_frozen_environment(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    home = tmp_path / "home"
    fake_uv = home / ".local" / "bin" / "uv"
    log = tmp_path / "uv-calls.log"
    fake_uv.parent.mkdir(parents=True)
    fake_uv.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$0 $*\" >> \"$FAKE_UV_LOG\"\n"
        "app=''\n"
        "previous=''\n"
        "for value in \"$@\"; do\n"
        "  if [ \"$previous\" = '--directory' ]; then app=$value; fi\n"
        "  previous=$value\n"
        "done\n"
        "case \" $* \" in\n"
        "  *' sync '*) mkdir -p \"$app/.venv\" ;;\n"
        "  *\"platform.python_version\"*) printf '%s\\n' '3.13.14' ;;\n"
        "  *\"import yaml, mcp, pydantic, m32_bridge\"*) printf '%s\\n' 'READY' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    monkeypatch.setenv("FAKE_UV_LOG", str(log))
    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=home,
        uv_state=RuntimeManagerState(uv_status="installed_user_local"),
    )
    result.update({"bootstrap_apply": True, "uv_bin": str(fake_uv)})

    applied = script_runtime.perform_apply_install("posix", result)

    calls = log.read_text(encoding="utf-8")
    assert applied["ok"] is True
    assert applied["runtime_info"]["application_runtime_ready"] is True
    assert applied["runtime_info"]["managed_python_version"] == "3.13.14"
    assert calls.count(str(fake_uv)) == 3
    assert " sync --frozen --managed-python --python 3.13" in calls
    assert calls.count(" run --frozen --managed-python --python 3.13") == 2
    assert all(token not in calls.lower() for token in ("sudo", "apt ", "yum ", "dnf ", " pip "))
    assert applied["runtime_info"]["network_scan"] == "not_run"
    assert applied["runtime_info"]["console_probe"] == "not_run"
    assert applied["osc_writes_sent"] == 0


def test_missing_uv_path_is_controlled_before_launcher_creation(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    home = tmp_path / "home"
    result = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=home,
        uv_state=RuntimeManagerState(uv_status="installed_user_local"),
    )
    monkeypatch.delenv("M32_INSTALL_UV_BIN", raising=False)
    non_executable = tmp_path / "runtime" / "uv"
    non_executable.parent.mkdir(parents=True)
    non_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    non_executable.chmod(0o644)

    for invalid_uv in (str(tmp_path / "missing" / "uv"), "relative/uv", str(non_executable)):
        applied = script_runtime.perform_apply_install(
            "posix",
            result,
            bootstrap_apply=True,
            uv_bin=invalid_uv,
        )

        assert applied["ok"] is False
        assert applied["error_code"] == "UV_EXECUTABLE_UNAVAILABLE"
        assert applied["runtime_info"]["failed_step"] == "uv_reuse"
        assert applied["runtime_info"]["application_runtime_ready"] is False
        assert applied["runtime_info"]["full_tty_allowed"] is False
        assert applied["system_python_modified"] is False
        assert applied["runtime_info"]["admin_used"] is False
        assert applied["osc_writes_sent"] == 0
        assert "Traceback" not in applied["message"]
        assert not Path(result["launcher_path"]).exists()


def test_posix_clean_host_reuses_new_uv_in_same_tty_process(tmp_path):
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.log"
    remote_script = tmp_path / "downloaded" / "install.sh"
    remote_script.parent.mkdir()
    remote_script.write_text(POSIX_INSTALLER.read_text(encoding="utf-8"), encoding="utf-8")
    remote_script.chmod(0o755)
    source_archive = tmp_path / "source.tar.gz"
    with tarfile.open(source_archive, "w:gz") as archive:
        archive.add(ROOT / "pyproject.toml", arcname="m32-bridge-main/pyproject.toml")
        archive.add(ROOT / "uv.lock", arcname="m32-bridge-main/uv.lock")
        archive.add(ROOT / ".python-version", arcname="m32-bridge-main/.python-version")
        archive.add(ROOT / "src", arcname="m32-bridge-main/src")
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/bin/sh\n"
        "target=''\n"
        "previous=''\n"
        "for value in \"$@\"; do\n"
        "  if [ \"$previous\" = '-o' ]; then target=$value; fi\n"
        "  previous=$value\n"
        "done\n"
        "case \" $* \" in\n"
        "  *'astral.sh/uv/install.sh'*)\n"
        "    printf '%s\\n' '#!/bin/sh' > \"$target\"\n"
        "    printf '%s\\n' 'mkdir -p \"$HOME/.local/bin\"' >> \"$target\"\n"
        "    printf '%s\\n' 'cp \"$FAKE_UV_TEMPLATE\" \"$HOME/.local/bin/uv\"' >> \"$target\"\n"
        "    printf '%s\\n' 'chmod +x \"$HOME/.local/bin/uv\"' >> \"$target\"\n"
        "    ;;\n"
        "  *) cp \"$FAKE_SOURCE_ARCHIVE\" \"$target\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    fake_python = tmp_path / "python3.13"
    fake_python.write_text("#!/bin/sh\nprintf '%s\\n' 'Python 3.13.14'\n", encoding="utf-8")
    fake_python.chmod(0o755)
    fake_uv_template = tmp_path / "uv-template"
    bootstrap_runner = tmp_path / "bootstrap-runner.py"
    bootstrap_runner.write_text(
        "import subprocess, sys\n"
        "args = [value for value in sys.argv[1:] if value not in {'--tty', '--color'}]\n"
        "completed = subprocess.run([sys.executable, *args], stdin=subprocess.DEVNULL, capture_output=True, text=True)\n"
        "sys.stdout.write(completed.stdout)\n"
        "sys.stderr.write(completed.stderr)\n"
        "raise SystemExit(completed.returncode)\n",
        encoding="utf-8",
    )
    fake_uv_template.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$0 $*\" >> \"$FAKE_UV_LOG\"\n"
        "app=''\n"
        "previous=''\n"
        "for value in \"$@\"; do\n"
        "  if [ \"$previous\" = '--directory' ]; then app=$value; fi\n"
        "  previous=$value\n"
        "done\n"
        "case \" $* \" in\n"
        "  *' --version '*) printf '%s\\n' 'uv 0.12.1' ;;\n"
        "  *' python find '*) printf '%s\\n' \"$FAKE_MANAGED_PYTHON\" ;;\n"
        "  *' sync '*) mkdir -p \"$app/.venv\" ;;\n"
        "  *\"platform.python_version\"*) printf '%s\\n' '3.13.14' ;;\n"
        "  *\"import yaml, mcp, pydantic, m32_bridge\"*) printf '%s\\n' 'READY' ;;\n"
        "  *' run '*)\n"
        "    while [ \"$#\" -gt 0 ] && [ \"$1\" != 'python' ]; do shift; done\n"
        "    shift\n"
        "    \"$FAKE_BOOTSTRAP_PYTHON\" \"$FAKE_BOOTSTRAP_RUNNER\" \"$@\"\n"
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_uv_template.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "TERM": "dumb",
            "FAKE_UV_TEMPLATE": str(fake_uv_template),
            "FAKE_SOURCE_ARCHIVE": str(source_archive),
            "FAKE_UV_LOG": str(uv_log),
            "FAKE_MANAGED_PYTHON": str(fake_python),
            "FAKE_BOOTSTRAP_PYTHON": sys.executable,
            "FAKE_BOOTSTRAP_RUNNER": str(bootstrap_runner),
        }
    )

    master_fd, slave_fd = os.openpty()
    process = subprocess.Popen(
        ["/bin/sh", str(remote_script)],
        cwd=remote_script.parent,
        env=env,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
    )
    os.close(slave_fd)
    output = bytearray()

    def read_until(marker: bytes, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while marker not in output and time.monotonic() < deadline:
            readable, _, _ = select.select([master_fd], [], [], 0.2)
            if readable:
                chunk = os.read(master_fd, 65536)
                if not chunk:
                    break
                output.extend(chunk)
        assert marker in output, output.decode(errors="replace")

    try:
        read_until(b"Select [1-3]:")
        os.write(master_fd, b"1\n")
        read_until(b"Type INSTALL to continue.")
        os.write(master_fd, b"INSTALL\n")
        deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < deadline:
            readable, _, _ = select.select([master_fd], [], [], 0.2)
            if readable:
                chunk = os.read(master_fd, 65536)
                if not chunk:
                    break
                output.extend(chunk)
        process.wait(timeout=2)
        while True:
            readable, _, _ = select.select([master_fd], [], [], 0)
            if not readable:
                break
            try:
                chunk = os.read(master_fd, 65536)
                if not chunk:
                    break
                output.extend(chunk)
            except OSError:
                break
    finally:
        os.close(master_fd)

    rendered = output.decode(errors="replace")

    expected_uv = str(home / ".local" / "bin" / "uv")
    assert process.returncode == 0, rendered
    assert uv_log.exists(), rendered
    calls = uv_log.read_text(encoding="utf-8")
    assert "status: already_current" in rendered
    assert expected_uv in calls
    assert "run --managed-python --python 3.13 --no-build --no-project" in calls
    assert "run --frozen --managed-python --python 3.13 --no-build --no-project" not in calls
    assert "sync --frozen --managed-python --python 3.13 --no-build --no-install-project" in calls
    assert calls.count("run --frozen --managed-python --python 3.13 --no-build --no-sync") == 2
    assert "uv 0.12.1" in rendered
    assert "Python 3.13.14" in rendered
    assert "github_release_or_archive" in rendered
    assert "\x1b[" not in rendered
    assert (home / ".m32-bridge" / "app" / ".venv").is_dir()
    assert (home / ".local" / "bin" / "m32-bridge").is_file()
    assert not (Path(env.get("TMPDIR", "/tmp")) / f"m32-bridge-bootstrap-{process.pid}").exists()
    assert "Open a new terminal" not in rendered
    assert "export PATH" not in rendered

    launcher = home / ".local" / "bin" / "m32-bridge"
    before_launch = calls.count(expected_uv)
    desktop_env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "FAKE_UV_LOG": str(uv_log),
        "FAKE_BOOTSTRAP_PYTHON": sys.executable,
        "FAKE_BOOTSTRAP_RUNNER": str(bootstrap_runner),
    }
    launched = subprocess.run(
        [str(launcher), "--help"],
        cwd=tmp_path,
        env=desktop_env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    launcher_calls = uv_log.read_text(encoding="utf-8")
    assert launched.returncode == 0, launched.stderr
    assert launcher_calls.count(expected_uv) == before_launch + 1
    assert str(launcher) == launched.args[0]
    assert str(tmp_path) != str(home / ".m32-bridge" / "app")
    assert "PYTHONPATH" not in desktop_env
    assert "M32_INSTALL_UV_BIN" not in desktop_env
    assert "--project" in launcher_calls.splitlines()[-1]
    assert "--no-build --no-sync" in launcher_calls.splitlines()[-1]
