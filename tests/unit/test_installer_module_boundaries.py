from __future__ import annotations


def test_installer_modules_import_without_side_effects():
    import m32_bridge.installer.output as output
    import m32_bridge.installer.paths as paths
    import m32_bridge.installer.planner as planner
    import m32_bridge.installer.platforms as platforms
    import m32_bridge.installer.runtime_manager as runtime_manager
    import m32_bridge.installer.service as service
    import m32_bridge.installer.state as state
    import m32_bridge.installer.verification as verification

    assert output.build_installer_output
    assert platforms.InstallationTarget
    assert paths.default_install_location
    assert runtime_manager.RuntimeManagerState
    assert state.InstallationState
    assert planner.plan_dry_run_install
    assert service.installer_status
    assert verification.render_post_install_verification


def test_installer_service_boundary_does_not_contact_console_or_write_osc(tmp_path):
    from installer_test_helpers import isolated_install_home

    from m32_bridge.installer.service import installer_status

    home = isolated_install_home(tmp_path)
    result = installer_status(
        platform="macos",
        home=home.posix_home,
        local_app_data=home.windows_local_app_data,
        dry_run=True,
    )

    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
    assert result["app_path"] == str(home.posix_app_path)
    assert result["launcher_path"] == str(home.posix_launcher_path)
