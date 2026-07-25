"""External Patrick-Gilles Maillot X32 Emulator read/sync gate.

These tests require a running external emulator. They intentionally do not
fallback to Fake M32 and do not send OSC writes.
"""

from __future__ import annotations

import os

import pytest

from m32_bridge.mcp.read_tools import overview
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTimeoutError
from m32_bridge.osc.transport import OscTransport


def _target() -> tuple[str, int]:
    host = os.environ.get("M32_EXTERNAL_EMULATOR_HOST")
    port = os.environ.get("M32_EXTERNAL_EMULATOR_PORT")
    if not host or not port:
        pytest.fail("M32_EXTERNAL_EMULATOR_HOST and M32_EXTERNAL_EMULATOR_PORT are required for T085")
    return host, int(port)


def _transport() -> OscTransport:
    host, port = _target()
    return OscTransport(host, port, timeout=1.0)


def _read_optional_capability(address: str, *args: object) -> dict[str, object]:
    try:
        message = _transport().request(address, *args)
    except OscTimeoutError as exc:
        return {"supported": False, "status": "unsupported_or_timeout", "error": str(exc)}
    if message.arguments and str(message.arguments[0]).upper() == "UNSUPPORTED_PATH":
        return {"supported": False, "status": "unsupported_or_timeout", "reply": message.arguments}
    return {"supported": True, "status": "supported", "reply_address": message.address, "reply": message.arguments}


def test_external_emulator_identity_responds_to_info():
    message = _transport().request("/info")

    assert message.address == "/info"
    assert len(message.arguments) >= 3
    assert "emulator" in str(message.arguments[1]).lower()
    assert str(message.arguments[2]).upper() == "X32"


def test_external_emulator_leaf_read_and_reconnect():
    first = _transport().request("/ch/01/mix/fader")
    second = _transport().request("/ch/01/config/name")
    reconnect = _transport().request("/-stat/selidx")

    assert first.address == "/ch/01/mix/fader"
    assert isinstance(first.arguments[0], float)
    assert second.address == "/ch/01/config/name"
    assert isinstance(second.arguments[0], str)
    assert reconnect.address == "/-stat/selidx"


def test_external_emulator_known_capability_limitations_are_classified():
    info = _transport().request("/info")
    fader = _transport().request("/ch/01/mix/fader")
    name = _transport().request("/ch/01/config/name")
    selected = _transport().request("/-stat/selidx")

    assert info.address == "/info"
    assert fader.address == "/ch/01/mix/fader"
    assert name.address == "/ch/01/config/name"
    assert selected.address == "/-stat/selidx"

    node = _read_optional_capability("/node", "/")
    meters = _read_optional_capability("/meters")

    assert node["status"] in {"supported", "unsupported_or_timeout"}
    assert meters["status"] in {"supported", "unsupported_or_timeout"}


def test_external_emulator_overview_classifies_optional_timeouts_as_partial_capability():
    result = overview(OscClient(_transport()))

    assert result["connection_lifecycle"] == "connected"
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["data"]["configured_host"] == _target()[0]
    assert result["data"]["configured_port"] == _target()[1]
    assert result["status"] in {"connected", "degraded"}
    if result["status"] == "degraded":
        assert result["error_code"] == "PARTIAL_CAPABILITY"
        assert result["unsupported_or_timeout_paths"]
