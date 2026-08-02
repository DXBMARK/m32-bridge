from __future__ import annotations


def test_partial_failure_guidance_never_claims_success(tmp_path):
    from m32_bridge.installer.lifecycle import render_lifecycle_guidance

    guidance = render_lifecycle_guidance(surface="posix", home=tmp_path, install_status="partial_failure")

    recovery = guidance["partial_failure_recovery"]
    assert guidance["ok"] is False
    assert guidance["result_status"] == "partial_failure"
    assert recovery["ok"] is False
    assert recovery["claims_success"] is False
    assert recovery["recommended_action"] == "repair"
    assert recovery["manual_recovery_steps"]
    assert recovery["osc_writes_sent"] == 0
    assert recovery["hardware_verified"] is False
    assert recovery["production_live_ready"] is False


def test_installer_partial_failure_output_includes_lifecycle_recovery(tmp_path):
    from m32_bridge.installer.script_runtime import build_install_result
    from m32_bridge.installer.runtime_manager import RuntimeManagerState

    marker = tmp_path / ".m32-bridge" / ".partial_failure"
    marker.parent.mkdir(parents=True)
    marker.write_text("failed", encoding="utf-8")

    result = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    assert result["status"] == "partial_failure"
    assert result["ok"] is False
    assert result["lifecycle_guidance"]["app_path"] == result["app_path"]
    assert result["lifecycle_guidance"]["launcher_path"] == result["launcher_path"]
    assert result["lifecycle_guidance"]["partial_failure_recovery"]["claims_success"] is False
    assert "repair" in result["lifecycle_guidance"]["partial_failure_recovery"]["recommended_action"]


def test_failed_guidance_never_claims_success_and_release_capabilities_are_current(tmp_path):
    from m32_bridge.installer.lifecycle import render_lifecycle_guidance

    guidance = render_lifecycle_guidance(surface="posix", home=tmp_path, install_status="failed")

    assert guidance["ok"] is False
    assert guidance["result_status"] == "failed"
    assert guidance["partial_failure_recovery"]["claims_success"] is False
    assert guidance["partial_failure_recovery"]["recommended_action"] == "repair"
    assert guidance["release_guidance"]["release_manifest"] == "implemented"
    assert guidance["release_guidance"]["sha256_checksums"] == "implemented"
    future = {item["kind"] for item in guidance["future_packaging"]}
    assert "checksums" not in future
    assert "GitHub Releases" not in future
