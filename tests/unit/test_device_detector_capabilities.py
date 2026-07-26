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


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_optional_capability_timeouts_are_reported_as_structured_limitations():
    from m32_bridge.diagnostics.device_identity import classify_device

    payload = classify_device(
        configured_host="192.0.2.10",
        configured_port=10023,
        intended_target_type="emulator",
        info_probe={
            "udp_info_probe_result": "CONNECTED",
            "attempted_path": "/info",
            "connected": True,
            "response_address": ["192.0.2.10", 10023],
            "latency_ms": 2,
            "exception_type": None,
            "info_raw": ["X32-Edit-Emulator", "4.13", 1],
            "osc_writes_sent": 0,
        },
        optional_capability_results=[
            {
                "path": "/node",
                "status": "TIMEOUT",
                "reason": "Optional overview path timed out",
                "exception_type": "OscTimeoutError",
            },
            {
                "path": "/meters",
                "status": "UNSUPPORTED",
                "reason": "Emulator does not expose meters",
                "exception_type": None,
            },
        ],
    )

    Draft202012Validator(_schema()).validate(payload)
    assert payload["connected"] is True
    assert payload["status"] in {"PARTIAL_CAPABILITY", "CAPABILITY_LIMITATION"}
    assert payload["error_code"] in {"PARTIAL_CAPABILITY", "CAPABILITY_LIMITATION"}
    assert payload["error_code"] != "NOT_CONNECTED"
    assert payload["unsupported_or_timeout_paths"] == [
        {
            "path": "/node",
            "status": "TIMEOUT",
            "reason": "Optional overview path timed out",
            "exception_type": "OscTimeoutError",
        },
        {
            "path": "/meters",
            "status": "UNSUPPORTED",
            "reason": "Emulator does not expose meters",
            "exception_type": None,
        },
    ]
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_unsupported_or_timeout_paths_reject_string_items_in_runtime_schema():
    invalid_payload = {
        "ok": True,
        "status": "PARTIAL_CAPABILITY",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "unsupported_or_timeout_paths": ["/node"],
    }

    errors = list(Draft202012Validator(_schema()).iter_errors(invalid_payload))

    assert any(list(error.path) == ["unsupported_or_timeout_paths", 0] for error in errors)
