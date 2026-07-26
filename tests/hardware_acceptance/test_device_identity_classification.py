from __future__ import annotations


def _physical_candidate_probe() -> dict:
    return {
        "udp_info_probe_result": "CONNECTED",
        "attempted_path": "/info",
        "configured_host": "192.0.2.20",
        "configured_port": 10023,
        "connected": True,
        "response_address": ["192.0.2.20", 10023],
        "latency_ms": 3,
        "exception_type": None,
        "info_raw": ["M32", "4.13", 12],
        "osc_writes_sent": 0,
    }


def test_hardware_verified_is_not_set_without_fixture_acceptance_evidence():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host="192.0.2.20",
        configured_port=10023,
        intended_target_type="hardware",
        info_probe=_physical_candidate_probe(),
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
    assert payload["osc_writes_sent"] == 0


def test_hardware_verified_requires_fixture_only_acceptance_evidence_and_sends_no_writes():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host="192.0.2.20",
        configured_port=10023,
        intended_target_type="hardware",
        info_probe=_physical_candidate_probe(),
        usb_evidence={
            "usb_detected": True,
            "usb_device_name": "M32",
            "vendor_id": "1397",
            "product_id": "00d5",
            "usb_confidence": "high",
            "inspection_status": "checked",
            "limitations": ["fixture-only acceptance evidence; no live hardware access"],
            "usb_control_supported": False,
        },
        hardware_acceptance_evidence={
            "source": "fixture",
            "physical_suite_passed": True,
            "read_only": True,
            "writes_sent": 0,
        },
    )

    assert payload["classification"] == "HARDWARE_VERIFIED"
    assert payload["hardware_verified"] is True
    assert payload["production_live_ready"] is False
    assert payload["osc_writes_sent"] == 0
    assert payload["data"]["hardware_acceptance_evidence"]["source"] == "fixture"
    assert payload["data"]["hardware_acceptance_evidence"]["writes_sent"] == 0
