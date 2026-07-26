from __future__ import annotations


def test_os_recommendations_cover_supported_platforms_without_admin_defaults():
    from m32_bridge.diagnostics.os_recommendations import build_os_recommendations

    expected = {
        "darwin": "macos",
        "win32": "windows",
        "linux": "linux",
        "raspberry_pi_os": "raspberry_pi_os",
    }
    for platform_name, os_family in expected.items():
        payload = build_os_recommendations(platform_name=platform_name)

        assert payload["os_family"] == os_family
        assert payload["recommended_launcher"] == "m32-bridge"
        assert payload["user_local_default"] is True
        assert payload["admin_required"] in {"no", "optional"}
        assert payload["usb_detection"] == "best_effort"
        assert payload["osc_writes_sent"] == 0
        assert payload["hardware_verified"] is False
        assert payload["production_live_ready"] is False


def test_os_recommendations_include_platform_specific_local_stdio_guidance():
    from m32_bridge.diagnostics.os_recommendations import build_os_recommendations

    macos = build_os_recommendations(platform_name="darwin")
    windows = build_os_recommendations(platform_name="win32")
    linux = build_os_recommendations(platform_name="linux")
    pi = build_os_recommendations(platform_name="raspberry_pi_os")

    assert any("Claude Desktop" in item for item in macos["recommendations"])
    assert any("user" in item.lower() for item in windows["recommendations"])
    assert any("no cloud" in item.lower() for item in linux["warnings"])
    assert any("future" in item.lower() for item in pi["future_packaging_notes"])


def test_cli_setup_and_detect_outputs_include_os_recommendations():
    from m32_bridge.cli import detect_device_runtime, setup_runtime

    probe = {
        "udp_info_probe_result": "CONNECTED",
        "response_address": ["192.0.2.10", 10023],
        "latency_ms": 1,
        "exception_type": None,
    }
    setup_payload = setup_runtime(
        host="192.0.2.10",
        port=10023,
        target_type="emulator",
        save=False,
        probe_result=probe,
    )
    detect_payload = detect_device_runtime(
        host="192.0.2.10",
        port=10023,
        target_type="emulator",
        probe_result=probe,
    )

    assert setup_payload["data"]["os_recommendations"]["recommended_launcher"] == "m32-bridge"
    assert detect_payload["data"]["os_recommendations"]["usb_detection"] == "best_effort"
    assert setup_payload["osc_writes_sent"] == 0
    assert detect_payload["osc_writes_sent"] == 0
