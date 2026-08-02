from __future__ import annotations

from m32_bridge.cli import _build_parser, _run_command
from m32_bridge.installer.verification import render_post_install_verification


REQUIRED_COMMANDS = [
    "m32-bridge health",
    "m32-bridge setup",
    "m32-bridge get-info",
    "m32-bridge detect-device",
    "m32-bridge doctor-runtime",
]


def test_post_install_verification_guidance_lists_required_commands(tmp_path):
    result = render_post_install_verification(environ={"SHELL": "/bin/bash"}, home=tmp_path)

    assert result["ok"] is True
    assert result["status"] == "verification_guidance"
    assert result["version"]
    assert result["install_metadata_status"] == "metadata_missing"
    assert result["provenance_trusted"] is False
    assert result["install_source"] == "not_available"
    assert result["selection"] == "not_available"
    assert result["release_tag"] == "not_available"
    assert result["source_commit"] == "not_available"
    assert result["install_path"] == str(tmp_path / ".m32-bridge" / "app")
    assert result["launcher_path"] == str(tmp_path / ".local" / "bin" / "m32-bridge")
    assert result["next_commands"] == REQUIRED_COMMANDS
    assert result["path_updated"] is False
    assert result["detected_shell"] == "bash"
    assert result["os_family"] in {"macos", "linux", "wsl", "raspberry_pi_os", "windows"}
    assert result["uv_required"] is True
    assert result["python_managed_by_uv"] is True
    assert result["config_path"]
    assert result["config_present"] is False
    assert result["detected_clients"]
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_install_status_cli_returns_structured_verification_json(tmp_path):
    parser = _build_parser()
    args = parser.parse_args(["install-status", "--json", "--home", str(tmp_path)])

    result = _run_command(args)

    assert result["structured"] is True
    assert result["next_commands"] == REQUIRED_COMMANDS
    assert result["install_path"] == str(tmp_path / ".m32-bridge" / "app")
    assert result["launcher_path"] == str(tmp_path / ".local" / "bin" / "m32-bridge")


def test_verify_install_cli_is_no_write_and_no_console_by_default(tmp_path):
    parser = _build_parser()
    args = parser.parse_args(["verify-install", "--json", "--home", str(tmp_path)])

    result = _run_command(args)

    assert result["attempted_path"] is None
    assert result["console_probe_attempted"] is False
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_verification_uses_kernel_platform_instead_of_powershell_environment(
    tmp_path,
    monkeypatch,
):
    from m32_bridge.installer import verification
    from m32_bridge.installer.runtime_manager import (
        RuntimeManagerState,
    )

    monkeypatch.setattr(
        verification.sys,
        "platform",
        "linux",
    )
    monkeypatch.setattr(
        verification.platform,
        "machine",
        lambda: "x86_64",
    )
    monkeypatch.setattr(
        verification,
        "application_version",
        lambda *_args, **_kwargs: "1.2.3",
    )
    monkeypatch.setattr(
        verification,
        "detect_uv_status",
        lambda: RuntimeManagerState(
            uv_status="present"
        ),
    )
    monkeypatch.setattr(
        verification,
        "inspect_runtime",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        verification,
        "detect_ide_clients",
        lambda **_kwargs: [],
    )

    result = verification.render_post_install_verification(
        home=tmp_path,
        environ={
            "HOME": str(tmp_path),
            "SHELL": "/bin/bash",
            "PSModulePath": "/opt/microsoft/powershell/Modules",
            "LOCALAPPDATA": str(
                tmp_path / "AppData" / "Local"
            ),
        },
    )

    assert result["os_family"] == "linux"
    assert result["detected_shell"] == "bash"
    assert result["install_path"] == str(
        tmp_path / ".m32-bridge" / "app"
    )
    assert result["launcher_path"] == str(
        tmp_path / ".local" / "bin" / "m32-bridge"
    )
