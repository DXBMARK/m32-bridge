from __future__ import annotations

import time


def test_usb_detection_is_best_effort_and_non_blocking_when_backend_unavailable():
    from m32_bridge.diagnostics.usb import inspect_usb_evidence

    started = time.perf_counter()
    payload = inspect_usb_evidence(platform_name="linux", backend=None, timeout_s=0.01)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert payload["inspection_status"] in {"unavailable", "blocked", "unsupported_os"}
    assert payload["usb_control_supported"] is False
    assert payload["limitations"]


def test_usb_detection_backend_failure_does_not_raise_or_enable_control():
    from m32_bridge.diagnostics.usb import inspect_usb_evidence

    def failing_backend() -> list[dict]:
        raise PermissionError("USB inspection blocked")

    payload = inspect_usb_evidence(platform_name="darwin", backend=failing_backend, timeout_s=0.01)

    assert payload["inspection_status"] == "blocked"
    assert payload["usb_detected"] is None
    assert payload["usb_confidence"] == "unavailable"
    assert payload["usb_control_supported"] is False
    assert any("blocked" in item.lower() for item in payload["limitations"])


def test_usb_detection_evidence_never_authorizes_hardware_verification():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host="192.0.2.20",
        configured_port=10023,
        intended_target_type="hardware",
        info_probe={
            "udp_info_probe_result": "CONNECTED",
            "attempted_path": "/info",
            "connected": True,
            "response_address": ["192.0.2.20", 10023],
            "latency_ms": 2,
            "exception_type": None,
            "info_raw": ["M32", "4.13", 1],
            "osc_writes_sent": 0,
        },
        usb_evidence={
            "usb_detected": True,
            "usb_device_name": "M32",
            "vendor_id": "1397",
            "product_id": "00d5",
            "usb_confidence": "high",
            "inspection_status": "checked",
            "limitations": [],
            "usb_control_supported": False,
        },
        hardware_acceptance_evidence=None,
    )

    assert payload["classification"] == "HARDWARE_CANDIDATE"
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert payload["data"]["usb_evidence"]["usb_control_supported"] is False
