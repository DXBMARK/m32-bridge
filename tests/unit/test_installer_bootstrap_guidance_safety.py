from __future__ import annotations

from pathlib import Path

from m32_bridge.installer import mcp_guidance
from m32_bridge.installer import script_runtime


def test_deferred_mcp_guidance_does_not_read_runtime_config(
    monkeypatch,
    tmp_path,
):
    def unexpected_config_read(*args, **kwargs):
        raise AssertionError(
            "resolve_runtime_config must not run"
        )

    monkeypatch.setattr(
        mcp_guidance,
        "resolve_runtime_config",
        unexpected_config_read,
    )

    payload = mcp_guidance.render_mcp_guidance(
        environ={},
        home=tmp_path,
        os_family="linux",
        version="0.1.0",
        read_runtime_config=False,
    )

    assert payload["ok"] is True
    assert payload["status"] == "MCP_GUIDANCE_READY"
    assert payload["runtime_config_inspection"] == "not_checked"
    assert payload["console_configured"] is None
    assert payload["configured_host"] is None
    assert payload["configured_port"] is None
    assert payload["reads_saved_user_config_by_default"] is False
    assert payload["args"] == ["mcp-server"]
    assert payload["manual_copy_only"] is True
    assert payload["console_probe"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_bootstrap_guidance_uses_deferred_config_mode(
    monkeypatch,
    tmp_path,
):
    def unexpected_config_read(*args, **kwargs):
        raise AssertionError(
            "bootstrap guidance must not read runtime.yaml"
        )

    monkeypatch.setattr(
        mcp_guidance,
        "resolve_runtime_config",
        unexpected_config_read,
    )

    launcher = (
        tmp_path
        / ".local"
        / "bin"
        / "m32-bridge"
    )

    guidance, lifecycle = (
        script_runtime._post_install_guidance(
            "posix",
            {
                "launcher_path": str(launcher),
                "target_version": "0.1.0",
            },
            status="already_current",
        )
    )

    assert guidance["ok"] is True
    assert guidance["runtime_config_inspection"] == "not_checked"
    assert guidance["console_configured"] is None
    assert guidance["configured_host"] is None
    assert guidance["configured_port"] is None
    assert guidance["console_probe"] == "not_run"
    assert guidance["osc_writes_sent"] == 0
    assert lifecycle["result_status"] == "already_current"


def test_guidance_failure_does_not_reverse_ready_update(
    monkeypatch,
    tmp_path,
):
    install_root = tmp_path / ".m32-bridge"
    app = install_root / "app"
    launcher = (
        tmp_path
        / ".local"
        / "bin"
        / "m32-bridge"
    )
    config = install_root / "runtime.yaml"
    config.parent.mkdir(parents=True)

    original_config = (
        b"config_scope: user\n"
        b"host: 10.0.0.20\n"
        b"port: 11101\n"
        b"schema_version: '1'\n"
    )
    config.write_bytes(original_config)

    uv = tmp_path / "uv"
    uv.write_text("", encoding="utf-8")

    result = {
        "ok": True,
        "status": "update",
        "installer_can_continue": True,
        "app_path": str(app),
        "launcher_path": str(launcher),
        "target_version": "0.1.0",
        "application_version": "0.1.0",
        "install_source": "github_commit_archive",
        "source_ref": "e" * 40,
        "source_commit": "e" * 40,
        "selection": "commit",
        "platform": "linux",
        "architecture": "x86_64",
        "runtime_info": {},
        "recommendations": [],
        "source_status": {},
    }

    monkeypatch.setattr(
        script_runtime,
        "_resolve_uv_executable",
        lambda surface, uv_bin: str(uv),
    )
    monkeypatch.setattr(
        script_runtime,
        "_apply_user_local_install",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        script_runtime,
        "_synchronize_application_runtime",
        lambda *args, **kwargs: {
            "ready": True,
            "managed_python_version": "3.13.14",
            "required_imports": "ok",
        },
    )
    monkeypatch.setattr(
        script_runtime,
        "build_install_metadata",
        lambda *args, **kwargs: {
            "application_version": "0.1.0",
        },
    )
    monkeypatch.setattr(
        script_runtime,
        "write_install_metadata",
        lambda *args, **kwargs: None,
    )

    def fail_guidance(*args, **kwargs):
        raise RuntimeError("optional guidance failure")

    monkeypatch.setattr(
        script_runtime,
        "_post_install_guidance",
        fail_guidance,
    )

    completed = script_runtime.perform_apply_install(
        "posix",
        result,
        bootstrap_apply=True,
        uv_bin=str(uv),
    )

    assert completed["ok"] is True
    assert completed["status"] == "already_current"
    assert (
        completed["runtime_info"]["application_runtime_ready"]
        is True
    )
    assert completed["runtime_info"]["full_tty_allowed"] is True
    assert (
        completed["runtime_info"]["post_install_guidance_status"]
        == "MCP_GUIDANCE_DEFERRED"
    )
    assert (
        completed["mcp_guidance"]["status"]
        == "MCP_GUIDANCE_DEFERRED"
    )
    assert completed["mcp_guidance"]["console_probe"] == "not_run"
    assert completed["mcp_guidance"]["osc_writes_sent"] == 0
    assert config.read_bytes() == original_config
