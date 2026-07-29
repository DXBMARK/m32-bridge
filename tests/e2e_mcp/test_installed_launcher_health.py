from __future__ import annotations

from m32_bridge.installer.verification import launcher_verification_metadata


def test_posix_installed_launcher_health_metadata_without_console_connectivity(tmp_path):
    result = launcher_verification_metadata(surface="posix", home=tmp_path)

    assert result["command"] == "m32-bridge health"
    assert result["launcher_path"] == str(tmp_path / ".local" / "bin" / "m32-bridge")
    assert result["uses_global_py"] is False
    assert result["requires_console_config"] is False
    assert result["expected_write_count"] == 0
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_windows_installed_launcher_health_metadata_without_console_connectivity(tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    result = launcher_verification_metadata(surface="windows", local_app_data=local_app_data)

    assert result["command"] == "m32-bridge health"
    assert result["launcher_path"] == str(local_app_data / "M32Bridge" / "bin" / "m32-bridge.cmd")
    assert result["uses_global_py"] is False
    assert result["requires_console_config"] is False
    assert result["expected_write_count"] == 0
