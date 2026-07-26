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


def test_runtime_output_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(_schema())


def test_minimal_runtime_output_matches_schema():
    payload = {
        "ok": False,
        "status": "NO_CONSOLE_HOST",
        "error_code": "NO_CONSOLE_HOST",
        "message": "No console host is configured. Run m32-bridge setup.",
        "configured_host": None,
        "configured_port": None,
        "attempted_path": "/info",
        "latency_ms": None,
        "exception_type": None,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "data": {},
        "recommendations": ["Run m32-bridge setup"],
    }

    Draft202012Validator(_schema()).validate(payload)


def test_unsupported_or_timeout_paths_are_structured_objects():
    payload = {
        "ok": True,
        "status": "PARTIAL_CAPABILITY",
        "configured_host": "example.invalid",
        "configured_port": 10023,
        "attempted_path": "/info",
        "latency_ms": 5,
        "exception_type": None,
        "connected": True,
        "classification": "CONNECTED_UNVERIFIED",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "unsupported_or_timeout_paths": [
            {
                "path": "/node",
                "status": "unsupported_or_timeout",
                "reason": "UNSUPPORTED_PATH",
                "exception_type": None,
            }
        ],
        "data": {},
        "recommendations": [],
    }

    Draft202012Validator(_schema()).validate(payload)


def test_unsupported_or_timeout_path_requires_path_and_status():
    invalid_payload = {
        "ok": True,
        "status": "PARTIAL_CAPABILITY",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "unsupported_or_timeout_paths": [{"path": "/node"}],
    }

    validator = Draft202012Validator(_schema())
    errors = list(validator.iter_errors(invalid_payload))

    assert any(error.validator == "required" and "status" in error.message for error in errors)


def test_common_runtime_output_builder_emits_schema_valid_no_console_host_envelope():
    from m32_bridge.diagnostics.runtime_output import runtime_output

    payload = runtime_output(
        ok=False,
        status="NO_CONSOLE_HOST",
        error_code="NO_CONSOLE_HOST",
        message="No console host is configured. Run m32-bridge setup.",
        configured_host=None,
        configured_port=None,
        attempted_path="/info",
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        data={},
        recommendations=["Run m32-bridge setup"],
    )

    Draft202012Validator(_schema()).validate(payload)


def test_common_runtime_output_builder_rejects_nonzero_osc_writes():
    from m32_bridge.diagnostics.runtime_output import runtime_output

    payload = runtime_output(
        ok=True,
        status="CONNECTED",
        configured_host="example.invalid",
        configured_port=10023,
        attempted_path="/info",
        latency_ms=1,
        osc_writes_sent=1,
        hardware_verified=False,
        production_live_ready=False,
    )

    errors = list(Draft202012Validator(_schema()).iter_errors(payload))

    assert any(error.path and list(error.path) == ["osc_writes_sent"] for error in errors)


def test_feature_runtime_json_outputs_match_schema(tmp_path: Path):
    from m32_bridge.cli import (
        config_set_runtime,
        config_show_runtime,
        config_validate_runtime,
        detect_device_runtime,
        setup_runtime,
    )
    from m32_bridge.interactive_shell import non_interactive_shell_required

    validator = Draft202012Validator(_schema())
    config_path = tmp_path / "runtime.yaml"
    probe = {
        "udp_info_probe_result": "CONNECTED",
        "response_address": ["192.0.2.10", 10023],
        "latency_ms": 1,
        "exception_type": None,
    }
    outputs = [
        setup_runtime(host="192.0.2.10", port=10023, target_type="emulator", save=False, probe_result=probe),
        detect_device_runtime(host="192.0.2.10", port=10023, target_type="emulator", probe_result=probe),
        config_set_runtime(host="192.0.2.10", port=10023, config_path=config_path),
        config_show_runtime(config_path=config_path),
        config_validate_runtime(host="192.0.2.10", port=10023, config_path=config_path),
        non_interactive_shell_required(stdin_is_tty=False),
    ]

    for payload in outputs:
        validator.validate(payload)
        assert payload["osc_writes_sent"] == 0
        assert payload["production_live_ready"] is False


def test_shell_and_config_failure_outputs_match_schema(tmp_path: Path):
    from m32_bridge.cli import config_set_runtime, config_validate_runtime
    from m32_bridge.interactive_shell import dispatch_slash_command

    validator = Draft202012Validator(_schema())
    outputs = [
        config_validate_runtime(host="", port=10023, config_path=tmp_path / "runtime.yaml"),
        config_set_runtime(host=None, port=10023, config_path=tmp_path / "runtime.yaml"),
        dispatch_slash_command(
            "/unlock",
            connected=False,
            stale=False,
            reconciled=True,
            emergency_active=False,
            policy_allows_write_readiness=True,
        ),
    ]

    for payload in outputs:
        validator.validate(payload)
        assert payload["ok"] is False
        assert payload["osc_writes_sent"] == 0
