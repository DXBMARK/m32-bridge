from __future__ import annotations

import pytest

from m32_bridge.core.connection import ConnectionController
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.codec import OscCodecError
from m32_bridge.osc.transport import OscTimeoutError, OscTransport


def _transport(server: FakeM32Server, *, timeout: float = 0.05) -> OscTransport:
    return OscTransport(*server.address, timeout=timeout)


def _controller(server: FakeM32Server, *, timeout: float = 0.05) -> ConnectionController:
    return ConnectionController(
        OscClient(_transport(server, timeout=timeout)),
        required_paths=("/ch/01/headamp/gain", "/rta/source"),
    )


def test_malformed_packet_failure_raises_known_codec_error_and_sends_no_writes():
    server = FakeM32Server().start()
    try:
        server.failures.malformed_next = True

        with pytest.raises(OscCodecError):
            _transport(server).request("/info")

        assert server.write_packets == []
    finally:
        server.stop()


def test_delayed_response_times_out_and_connection_fails_closed_without_writes():
    server = FakeM32Server().start()
    try:
        controller = _controller(server, timeout=0.01)
        assert controller.reconcile_after_reconnect().status == "reconciled"

        server.failures.delayed_ms = 50
        result = controller.check_connection_health()

        assert result.status == "disconnected"
        assert result.reason == "HEARTBEAT_TIMEOUT"
        assert result.write_locked is True
        assert controller.write_locked is True
        assert server.write_packets == []
    finally:
        server.stop()


def test_duplicated_response_is_consumed_deterministically_without_writes():
    server = FakeM32Server().start()
    try:
        server.failures.duplicate_next = True

        first = _transport(server).request("/info")
        second = _transport(server).request("/info")

        assert first.arguments[0] == "M32"
        assert second.arguments[0] == "M32"
        assert server.failures.duplicate_next is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_dropped_response_times_out_and_write_guard_stays_fail_closed():
    server = FakeM32Server().start()
    try:
        controller = _controller(server)
        assert controller.reconcile_after_reconnect().status == "reconciled"

        server.failures.drop_next = True
        health = controller.check_connection_health()
        write = controller.run_guarded_write(lambda: server.set_value("/ch/01/mix/fader", -4.0, source="ai"))

        assert health.status == "disconnected"
        assert health.reason == "HEARTBEAT_TIMEOUT"
        assert write == {"status": "DENIED", "error_code": "DISCONNECTED"}
        assert server.write_packets == []
    finally:
        server.stop()


def test_out_of_order_response_is_reported_as_known_timeout_and_fails_closed():
    server = FakeM32Server().start()
    try:
        controller = _controller(server, timeout=0.05)
        assert controller.reconcile_after_reconnect().status == "reconciled"

        server.failures.out_of_order_next = True
        result = controller.check_connection_health()

        assert result.status == "disconnected"
        assert result.reason == "HEARTBEAT_TIMEOUT"
        assert result.write_locked is True
        assert server.failures.out_of_order_next is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_failure_reconnect_backoff_is_bounded_without_infinite_loop_or_writes():
    server = FakeM32Server().start()
    try:
        server.failures.disconnect = True
        controller = _controller(server, timeout=0.01)
        sleeps: list[float] = []

        result = controller.reconnect_with_backoff(max_attempts=3, initial_backoff_seconds=0.01, max_backoff_seconds=0.02, sleep=sleeps.append)

        assert result.status == "disconnected"
        assert result.reason == "RECONNECT_FAILED"
        assert result.attempts == 3
        assert sleeps == [0.01, 0.02]
        assert controller.write_locked is True
        assert server.write_packets == []
    finally:
        server.stop()
