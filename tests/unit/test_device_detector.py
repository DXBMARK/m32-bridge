from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "002-local-runtime-setup-and-device-verification"
    / "contracts"
    / "runtime-output.schema.json"
)


def _validate_runtime_output(payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)


def _connected_info_probe(host: str = "192.0.2.10", port: int = 10023) -> dict:
    return {
        "udp_info_probe_result": "CONNECTED",
        "attempted_path": "/info",
        "configured_host": host,
        "configured_port": port,
        "connected": True,
        "response_address": [host, port],
        "latency_ms": 2,
        "exception_type": None,
        "info_raw": ["M32", "4.13", 1],
        "osc_writes_sent": 0,
    }


def test_detect_device_without_config_returns_not_configured_and_no_writes():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host=None,
        configured_port=None,
        intended_target_type="unknown",
        info_probe=None,
    )

    _validate_runtime_output(payload)
    assert payload["classification"] == "NOT_CONFIGURED"
    assert payload["status"] in {"NOT_CONFIGURED", "NO_CONSOLE_HOST"}
    assert payload["connected"] is False
    assert payload["configured_host"] is None
    assert payload["configured_port"] is None
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False


def test_detect_device_classifies_explicit_emulator_connection_without_hardware_verification():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host="192.0.2.10",
        configured_port=10023,
        intended_target_type="emulator",
        info_probe=_connected_info_probe(),
    )

    _validate_runtime_output(payload)
    assert payload["classification"] == "EMULATOR_CONNECTED"
    assert payload["connected"] is True
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert payload["osc_writes_sent"] == 0


def test_detect_device_classifies_unknown_connected_endpoint_as_unverified():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host="192.0.2.10",
        configured_port=10023,
        intended_target_type="unknown",
        info_probe=_connected_info_probe(),
    )

    _validate_runtime_output(payload)
    assert payload["classification"] == "CONNECTED_UNVERIFIED"
    assert payload["connected"] is True
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert payload["osc_writes_sent"] == 0


def test_detect_device_reports_hardware_candidate_without_acceptance_evidence():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host="192.0.2.10",
        configured_port=10023,
        intended_target_type="hardware",
        info_probe=_connected_info_probe(),
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

    _validate_runtime_output(payload)
    assert payload["classification"] == "HARDWARE_CANDIDATE"
    assert payload["connected"] is True
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert payload["data"]["usb_evidence"]["usb_control_supported"] is False
    assert payload["osc_writes_sent"] == 0
