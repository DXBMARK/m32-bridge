from __future__ import annotations

from m32_bridge.core.connection import ConnectionController
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _controller(server: FakeM32Server, *, timeout: float = 0.05, freshness_seconds: float = 0.2) -> ConnectionController:
    return ConnectionController(
        OscClient(OscTransport(*server.address, timeout=timeout)),
        required_paths=("/ch/01/headamp/gain", "/rta/source"),
        freshness_seconds=freshness_seconds,
    )


def test_heartbeat_loss_detection_locks_writes_and_sends_no_osc_writes():
    server = FakeM32Server().start()
    try:
        controller = _controller(server)
        assert controller.reconcile_after_reconnect().status == "reconciled"

        server.failures.drop_next = True
        result = controller.check_connection_health()

        assert result.status == "disconnected"
        assert result.write_locked is True
        assert result.reconciled is False
        assert result.reason == "HEARTBEAT_TIMEOUT"
        assert controller.write_locked is True
        assert server.write_packets == []
    finally:
        server.stop()


def test_stale_state_detection_keeps_write_lock_until_reconciliation_refresh():
    server = FakeM32Server().start()
    try:
        controller = _controller(server, freshness_seconds=0.001)
        assert controller.reconcile_after_reconnect().status == "reconciled"
        controller.mark_reconciliation_stale_for_test()

        stale = controller.check_connection_health()
        denied = controller.require_reconciled_for_writes()

        assert stale.status == "stale"
        assert stale.reason == "STALE_STATE"
        assert stale.write_locked is True
        assert denied["allowed"] is False
        assert denied["reason"] == "STALE_STATE"
        assert server.write_packets == []

        refreshed = controller.reconcile_after_reconnect()
        assert refreshed.status == "reconciled"
        assert controller.require_reconciled_for_writes()["allowed"] is True
    finally:
        server.stop()


def test_disconnect_restart_requires_reconciliation_before_unlock():
    server = FakeM32Server().start()
    host, port = server.address
    controller = _controller(server)
    try:
        assert controller.reconcile_after_reconnect().status == "reconciled"
        server.stop()

        disconnected = controller.check_connection_health()
        unlock_before_reconnect = controller.request_unlock()

        assert disconnected.status == "disconnected"
        assert disconnected.write_locked is True
        assert unlock_before_reconnect["unlocked"] is False
        assert unlock_before_reconnect["reason"] == "RECONCILIATION_REQUIRED"

        restarted = FakeM32Server(host=host, port=port).start()
        try:
            controller.client = OscClient(OscTransport(host, port, timeout=0.05))
            reconnected = controller.reconnect_with_backoff(max_attempts=3, sleep=lambda _delay: None)
            unlock_after_reconcile = controller.request_unlock()

            assert reconnected.status == "reconciled"
            assert reconnected.attempts <= 3
            assert unlock_after_reconcile == {"unlocked": True, "write_locked": False, "reason": None}
            assert controller.identity["hardware_verified"] is False
            assert restarted.write_packets == []
        finally:
            restarted.stop()
    finally:
        if server._sock is not None:
            server.stop()


def test_reconnect_backoff_is_bounded_without_infinite_loop():
    server = FakeM32Server().start()
    host, port = server.address
    server.stop()
    controller = ConnectionController(OscClient(OscTransport(host, port, timeout=0.01)), required_paths=("/ch/01/headamp/gain",))
    sleeps: list[float] = []

    result = controller.reconnect_with_backoff(max_attempts=3, initial_backoff_seconds=0.01, max_backoff_seconds=0.02, sleep=sleeps.append)

    assert result.status == "disconnected"
    assert result.reason == "RECONNECT_FAILED"
    assert result.attempts == 3
    assert sleeps == [0.01, 0.02]
    assert controller.write_locked is True


def test_unreconciled_write_attempt_is_rejected_without_invoking_write_callback():
    server = FakeM32Server().start()
    try:
        controller = _controller(server)
        called = {"value": False}

        result = controller.run_guarded_write(lambda: called.__setitem__("value", True))

        assert result == {"status": "DENIED", "error_code": "RECONCILIATION_REQUIRED"}
        assert called["value"] is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_disconnected_and_stale_write_attempts_are_rejected_without_osc_writes():
    server = FakeM32Server().start()
    try:
        controller = _controller(server, freshness_seconds=0.001)
        assert controller.reconcile_after_reconnect().status == "reconciled"

        server.failures.drop_next = True
        controller.check_connection_health()
        disconnected_result = controller.run_guarded_write(lambda: server.set_value("/ch/01/mix/fader", -6.0, source="ai"))

        assert disconnected_result == {"status": "DENIED", "error_code": "DISCONNECTED"}
        assert server.write_packets == []

        assert controller.reconcile_after_reconnect().status == "reconciled"
        controller.mark_reconciliation_stale_for_test()
        controller.check_connection_health()
        stale_result = controller.run_guarded_write(lambda: server.set_value("/ch/01/mix/fader", -5.0, source="ai"))

        assert stale_result == {"status": "DENIED", "error_code": "STALE_STATE"}
        assert server.write_packets == []
    finally:
        server.stop()
