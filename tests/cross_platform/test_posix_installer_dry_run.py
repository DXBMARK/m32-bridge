from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess

import pytest

from m32_bridge.installer.planner import plan_dry_run_install


ROOT = Path(__file__).resolve().parents[2]
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"


def _install_sh_text() -> str:
    assert POSIX_INSTALLER.exists(), "T022 must add scripts/install.sh for the POSIX installer surface"
    return POSIX_INSTALLER.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("platform", "expected_platform"),
    [
        ("macos", "macos"),
        ("linux", "linux"),
        ("wsl", "wsl"),
        ("raspberry_pi_os", "raspberry_pi_os"),
    ],
)
def test_posix_dry_run_supports_user_local_targets_without_network(tmp_path, platform, expected_platform):
    home = tmp_path / "home" / "operator"

    result = plan_dry_run_install(platform=platform, home=home)

    assert result["platform"] == expected_platform
    assert result["app_path"] == str(home / ".m32-bridge" / "app")
    assert result["launcher_path"] == str(home / ".local" / "bin" / "m32-bridge")
    assert result["requires_admin"] is False
    assert result["global_py_required"] is False
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_posix_install_script_documents_supported_os_and_dry_run_status_only():
    text = _install_sh_text().lower()

    for expected in ["macos", "linux", "wsl", "raspberry pi os"]:
        assert expected in text
    assert "dry-run" in text or "dry_run" in text
    assert "osc_writes_sent=0" in text
    assert "no /set" in text
    assert "send_raw_osc" not in text
    assert "state-changing osc" not in text
    assert "webui" not in text
    assert "database" not in text


def test_posix_install_guidance_allows_curl_with_wget_or_manual_fallback():
    text = _install_sh_text().lower()

    assert "curl" in text
    assert "wget" in text or "manual download" in text
    assert "+971505121583" in text
    assert "download" in text
    assert "inspect" in text
    assert "user-local" in text or "$home/.m32-bridge" in text


def test_posix_script_supports_local_checkout_and_github_raw_bootstrap_modes():
    text = _install_sh_text()

    assert 'src/m32_bridge' in text
    assert 'pyproject.toml' in text
    assert 'INSTALL_SOURCE="local_checkout"' in text
    assert 'INSTALL_SOURCE="github_release_or_archive"' in text
    assert "M32_INSTALL_SOURCE_URL" in text
    assert "M32_INSTALL_SOURCE_REF" in text
    assert "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz" in text
    assert "m32-ai-mcp-bridge" not in text


def test_posix_remote_bootstrap_missing_uv_is_structured_not_success(tmp_path):
    script = tmp_path / "install.sh"
    script.write_text(_install_sh_text(), encoding="utf-8")
    script.chmod(0o755)
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["PATH"] = "/usr/bin:/bin"
    env["M32_INSTALL_SOURCE_URL"] = "https://github.com/example/m32/archive/refs/heads/main.tar.gz"

    completed = subprocess.run(
        ["/bin/sh", str(script), "--dry-run", "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "RUNTIME_SETUP_REQUIRED"
    assert payload["install_source"] in {"github_raw", "github_release_or_archive"}
    assert payload["source_url"] == "https://github.com/example/m32/archive/refs/heads/main.tar.gz"
    assert payload["installer_can_continue"] is False
    assert payload["required_actions"][0]["requires_confirmation"] is True
    assert payload["admin_required"] is False
    assert payload["global_python_required"] is False
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert payload["osc_writes_sent"] == 0


def test_posix_local_checkout_dry_run_uses_local_source_metadata(tmp_path):
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
    assert payload["install_source"] == "local_checkout"
    assert payload["source_url"]
    assert payload["installer_can_continue"] is True
    assert payload["required_actions"] == []
    assert payload["osc_writes_sent"] == 0


def test_posix_installer_wizard_mentions_dxbmark_style_without_raw_theme():
    text = _install_sh_text().lower()

    assert "dxbmark" in text
    assert "tty" in text
    assert "--tty --color" in text or "--tty" in text
    assert "48;2;36;57;71" in text
    assert "paint_tty_lines" in text
    assert "tput cols" in text
    assert "non-tty" in text or "non_tty" in text
    assert "system check" in text
    assert "source check" in text
    assert "install plan" in text
    assert "required actions" in text
    assert "json" in text
    assert "raw interactive theme" not in text
