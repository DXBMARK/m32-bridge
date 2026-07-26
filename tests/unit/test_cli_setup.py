from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_setup(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    env.pop("M32_CONSOLE_HOST", None)
    env.pop("M32_CONSOLE_PORT", None)
    return subprocess.run(
        ["uv", "run", "m32-bridge", "setup", *args, "--json"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _payload(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def test_setup_json_contract_for_valid_endpoint_reports_info_only_and_no_writes():
    from m32_bridge.cli import setup_runtime

    payload = setup_runtime(
        host="192.0.2.10",
        port=10023,
        target_type="emulator",
        save=False,
        probe_result={
            "udp_info_probe_result": "CONNECTED",
            "response_address": ["192.0.2.10", 10023],
            "latency_ms": 1,
            "exception_type": None,
        },
    )

    assert payload["ok"] is True
    assert payload["status"] in {"CONNECTED", "NOT_SAVED"}
    assert payload["configured_host"] == "192.0.2.10"
    assert payload["configured_port"] == 10023
    assert payload["attempted_path"] == "/info"
    assert payload["latency_ms"] is not None
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_setup_json_contract_for_invalid_host_returns_invalid_host():
    completed = _run_setup("--host", "", "--port", "10023", "--target-type", "unknown", "--no-save")

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["error_code"] == "INVALID_HOST"
    assert payload["configured_host"] is None
    assert payload["attempted_path"] == "/info"
    assert payload["osc_writes_sent"] == 0


def test_setup_json_contract_for_invalid_port_returns_invalid_port():
    completed = _run_setup("--host", "192.0.2.10", "--port", "70000", "--target-type", "unknown", "--no-save")

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["error_code"] == "INVALID_PORT"
    assert payload["configured_host"] == "192.0.2.10"
    assert payload["configured_port"] is None
    assert payload["osc_writes_sent"] == 0


def test_setup_json_contract_for_timeout_returns_structured_failure():
    completed = _run_setup(
        "--host",
        "127.0.0.1",
        "--port",
        "9",
        "--target-type",
        "unknown",
        "--timeout",
        "0.01",
        "--no-save",
    )

    assert completed.returncode != 0
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["error_code"] in {"CONNECT_TIMEOUT", "NOT_CONNECTED"}
    assert payload["configured_host"] == "127.0.0.1"
    assert payload["configured_port"] == 9
    assert payload["attempted_path"] == "/info"
    assert payload["latency_ms"] is not None
    assert payload["exception_type"] is not None
    assert payload["osc_writes_sent"] == 0


def test_setup_json_contract_for_unexpected_response_address_is_structured():
    from m32_bridge.cli import setup_runtime

    payload = setup_runtime(
        host="192.0.2.10",
        port=10023,
        target_type="unknown",
        save=False,
        probe_result={
            "udp_info_probe_result": "CONNECTED",
            "response_address": ["192.0.2.99", 10023],
            "latency_ms": 1,
            "exception_type": None,
        },
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "UNEXPECTED_RESPONSE_ADDRESS"
    assert payload["configured_host"] == "192.0.2.10"
    assert payload["configured_port"] == 10023
    assert payload["attempted_path"] == "/info"
    assert payload["osc_writes_sent"] == 0
