from __future__ import annotations


def test_installer_mcp_guidance_never_writes_claude_or_client_config(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    claude_dir = tmp_path / ".config" / "Claude"
    claude_dir.mkdir(parents=True)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before
    assert guidance["no_auto_config_write"] is True
    assert guidance["config_written"] is False
    assert guidance["app_opened"] is False
    assert all(client["config_written"] is False for client in guidance["client_guidance"])
    assert all(client["app_opened"] is False for client in guidance["client_guidance"])


def test_installer_apply_success_includes_manual_copy_mcp_guidance(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.runtime_manager import RuntimeManagerState

    source = tmp_path / "source"
    (source / "src" / "m32_bridge").mkdir(parents=True)
    (source / "pyproject.toml").write_text("[project]\nname='m32-bridge'\nversion='0.1.0'\n", encoding="utf-8")
    (source / "uv.lock").write_text("", encoding="utf-8")
    (source / "src" / "m32_bridge" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(script_runtime, "_repo_root", lambda: source)
    uv_bin = tmp_path / "runtime" / "uv"
    uv_bin.parent.mkdir(parents=True)
    uv_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv_bin.chmod(0o755)

    plan = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    result = script_runtime.perform_apply_install("posix", plan, uv_bin=str(uv_bin))

    assert result["ok"] is True
    assert result["mcp_guidance"]["manual_copy_only"] is True
    assert result["mcp_guidance"]["command"] == str(tmp_path / "home" / ".local" / "bin" / "m32-bridge")
    assert result["mcp_guidance"]["args"] == ["mcp-server"]
    assert result["mcp_guidance"]["config_written"] is False
