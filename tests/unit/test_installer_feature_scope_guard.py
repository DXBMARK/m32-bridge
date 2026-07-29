from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER_SRC_ROOT = ROOT / "src" / "m32_bridge" / "installer"
FEATURE_DIR = ROOT / "specs" / "003-cross-platform-installers-and-first-run-setup"


def _source_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in INSTALLER_SRC_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    ).lower()


def test_no_binary_installer_artifacts_are_created_for_feature_scope():
    forbidden_suffixes = {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage"}
    artifacts = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.lower() in forbidden_suffixes
    ]

    assert artifacts == []


def test_installer_source_scope_does_not_add_forbidden_surfaces():
    text = _source_text()

    forbidden = [
        "send_raw_osc",
        "set_any_path",
        "execute_shell",
        "subprocess.shell",
        "format_sd",
        "shutdown_console",
        "set_firmware",
        "enable_phantom",
        "set_sample_rate",
        "chatgpt tunnel",
        "remote mcp",
        "webui",
        "database",
        "microservice",
        "production_live_ready=true",
        "hardware_verified=true",
    ]

    for token in forbidden:
        assert token not in text


def test_installer_contracts_keep_future_packaging_and_no_admin_scope():
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [
            FEATURE_DIR / "spec.md",
            FEATURE_DIR / "plan.md",
            FEATURE_DIR / "quickstart.md",
            FEATURE_DIR / "contracts" / "installer-contract.md",
        ]
    ).lower()

    assert "future-only" in combined
    assert "no administrator privileges are required by default" in combined
    assert "hardware_verified=true" in combined
    assert "production_live_ready=true" in combined
    assert "do not claim" in combined

def test_us1_installer_scripts_are_text_surfaces_not_binary_installers():
    install_sh = ROOT / "scripts" / "install.sh"
    install_ps1 = ROOT / "scripts" / "install.ps1"

    assert install_sh.exists()
    assert install_ps1.exists()
    assert install_sh.suffix == ".sh"
    assert install_ps1.suffix == ".ps1"
    assert "m32_bridge.installer.script_runtime" in install_sh.read_text(encoding="utf-8")
    assert "m32_bridge.installer.script_runtime" in install_ps1.read_text(encoding="utf-8")


def test_installer_runtime_rejects_system_paths_and_forbidden_commands(tmp_path):
    from m32_bridge.installer.script_runtime import _assert_user_local_result

    result = {
        "app_path": "/usr/local/m32-bridge/app",
        "launcher_path": str(tmp_path / "bin" / "m32-bridge"),
        "install_root": "/usr/local/m32-bridge",
        "required_actions": [
            {
                "action_id": "INSTALL_UV_USER_LOCAL",
                "title": "Install uv in user space",
                "reason": "runtime missing",
                "command_preview": "curl -LsSf https://astral.sh/uv/install.sh",
                "requires_confirmation": True,
                "risk_level": "user_local",
                "target_paths": [str(tmp_path / ".local" / "bin" / "uv")],
                "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
                "user_can_skip": False,
            }
        ],
    }

    try:
        _assert_user_local_result("posix", result)
    except ValueError as exc:
        assert "system path" in str(exc).lower()
    else:
        raise AssertionError("system path should be rejected")


def test_required_action_previews_do_not_use_admin_or_destructive_cleanup():
    from m32_bridge.installer.script_runtime import _uv_required_action

    for surface in ("posix", "windows"):
        action = _uv_required_action(surface, Path("/Users/operator"))
        preview = action["command_preview"].lower()
        assert "sudo" not in preview
        assert "runas" not in preview
        assert "rm -rf" not in preview
        assert "del /" not in preview
        assert action["requires_confirmation"] is True


def test_whole_feature_outputs_keep_no_write_and_no_readiness_claims(tmp_path):
    from m32_bridge.installer.first_run import non_tty_setup_response, run_setup_probe
    from m32_bridge.installer.lifecycle import render_lifecycle_guidance
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance
    from m32_bridge.installer.runtime_manager import RuntimeManagerState
    from m32_bridge.installer.script_runtime import build_install_result
    from m32_bridge.installer.verification import render_post_install_verification

    outputs = [
        build_install_result(
            surface="posix",
            platform="linux",
            dry_run=True,
            home=tmp_path,
            uv_state=RuntimeManagerState(uv_status="present"),
        ),
        non_tty_setup_response(environ={"SHELL": "/bin/bash"}, home=tmp_path),
        run_setup_probe(
            host="192.0.2.10",
            port=10023,
            target_type="emulator",
            confirm_save=False,
            home=tmp_path,
            probe_result={
                "udp_info_probe_result": "CONNECTED",
                "response_address": ["192.0.2.10", 10023],
                "latency_ms": 1,
                "exception_type": None,
            },
        ),
        render_post_install_verification(environ={}, home=tmp_path),
        render_mcp_guidance(environ={}, home=tmp_path, os_family="linux"),
        render_lifecycle_guidance(surface="posix", home=tmp_path),
    ]

    for payload in outputs:
        assert payload["osc_writes_sent"] == 0
        assert payload["hardware_verified"] is False
        assert payload["production_live_ready"] is False


def test_final_safety_inventory_excludes_forbidden_installer_surfaces():
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [
            *INSTALLER_SRC_ROOT.rglob("*.py"),
            ROOT / "scripts" / "install.sh",
            ROOT / "scripts" / "install.ps1",
            FEATURE_DIR / "quickstart.md",
        ]
        if path.is_file() and "__pycache__" not in path.parts
    ).lower()

    forbidden = [
        "signed release available",
        "webui started",
        "database connection",
        "background daemon started",
        "remote/cloud mcp available",
        "chatgpt tunnel started",
        "claude config written",
        "hardware_verified = true",
        "production_live_ready = true",
        '"hardware_verified": true',
        '"production_live_ready": true',
        "send_raw_osc",
        "execute_shell",
    ]
    for token in forbidden:
        assert token not in combined
