from __future__ import annotations

from m32_bridge.installer.support_matrix import (
    INSTALLER_TARGETS,
    release_supported_targets,
    target_by_id,
    target_for_installer_platform,
)


def test_installer_target_matrix_declares_verified_uv_platforms():
    targets = {target.target_id: target for target in INSTALLER_TARGETS}

    assert set(targets) == {
        "linux_x86_64_cp313",
        "wsl_x86_64_cp313",
        "macos_arm64_cp313",
        "macos_x86_64_cp313",
        "windows_amd64_cp313",
        "raspberry_pi_os_arm64_cp313",
    }
    assert {target.python_tag for target in targets.values()} == {"cp313"}
    assert {target.python_version for target in targets.values()} == {"3.13"}
    assert targets["linux_x86_64_cp313"].uv_platform == "x86_64-manylinux_2_17"
    assert targets["wsl_x86_64_cp313"].uv_platform == "x86_64-manylinux_2_17"
    assert targets["macos_arm64_cp313"].uv_platform == "aarch64-apple-darwin"
    assert targets["macos_x86_64_cp313"].uv_platform == "x86_64-apple-darwin"
    assert targets["windows_amd64_cp313"].uv_platform == "x86_64-pc-windows-msvc"
    assert targets["raspberry_pi_os_arm64_cp313"].uv_platform == "aarch64-manylinux_2_17"


def test_release_support_is_explicit_and_never_hides_a_missing_wheel():
    assert {target.target_id for target in release_supported_targets()} == {
        "linux_x86_64_cp313",
        "wsl_x86_64_cp313",
        "macos_arm64_cp313",
        "windows_amd64_cp313",
        "raspberry_pi_os_arm64_cp313",
    }

    intel = target_by_id("macos_x86_64_cp313")
    assert intel.release_supported is False
    assert intel.blocked_dependency == "cryptography==49.0.0"
    assert "wheel" in intel.support_blocker.lower()


def test_installer_platform_and_architecture_resolve_to_central_target():
    assert target_for_installer_platform("linux", "x86_64").target_id == "linux_x86_64_cp313"
    assert target_for_installer_platform("wsl", "amd64").target_id == "wsl_x86_64_cp313"
    assert target_for_installer_platform("macos", "arm64").target_id == "macos_arm64_cp313"
    assert target_for_installer_platform("windows_powershell", "AMD64").target_id == "windows_amd64_cp313"
    assert target_for_installer_platform("raspberry_pi_os", "aarch64").target_id == "raspberry_pi_os_arm64_cp313"
