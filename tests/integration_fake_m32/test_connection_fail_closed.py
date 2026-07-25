import pytest

from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.discovery import discover_identity
from m32_bridge.osc.transport import OscTimeoutError, OscTransport


def test_udp_timeout_locks_writes_by_failure_signal():
    server = FakeM32Server().start()
    try:
        host, port = server.address
        server.failures.drop_next = True
        transport = OscTransport(host, port, timeout=0.05)
        with pytest.raises(OscTimeoutError):
            transport.request("/info")
    finally:
        server.stop()


def test_unknown_firmware_is_write_locked():
    server = FakeM32Server().start()
    try:
        server.state.firmware = ""
        server.state.values["/-stat/firmware"] = ""
        host, port = server.address
        result = discover_identity(OscTransport(host, port))
        assert result.write_locked is True
        assert result.identity.firmware_status == "unknown"
    finally:
        server.stop()

