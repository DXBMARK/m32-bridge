from __future__ import annotations

import time


def test_usb_recommendation_handles_blocked_inspection_without_blocking():
    from m32_bridge.diagnostics.os_recommendations import usb_recommendation

    started = time.perf_counter()
    payload = usb_recommendation(
        usb_evidence={
            "inspection_status": "blocked",
            "limitations": ["USB inspection blocked"],
            "usb_control_supported": False,
        }
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert payload["status"] == "USB_INSPECTION_LIMITED"
    assert payload["blocking"] is False
    assert payload["usb_control_supported"] is False
    assert payload["osc_writes_sent"] == 0
    assert any("continuing" in item.lower() for item in payload["recommendations"])


def test_doctor_runtime_cli_output_includes_os_recommendations_without_probe_writes():
    from m32_bridge.cli import doctor_runtime_command

    payload = doctor_runtime_command(host=None, port=None, timeout=0.01, environ={})

    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["os_recommendations"]["usb_detection"] == "best_effort"
    assert payload["os_recommendations"]["recommended_launcher"] == "m32-bridge"
