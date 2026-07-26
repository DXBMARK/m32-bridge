from __future__ import annotations


def _unlock(**kwargs):
    from m32_bridge.interactive_shell import LocalShellState, dispatch_slash_command

    state = LocalShellState(write_locked=True)
    return dispatch_slash_command("/unlock", shell_state=state, **kwargs)


def test_unlock_denied_when_disconnected_with_zero_writes():
    payload = _unlock(connected=False, stale=False, reconciled=True, emergency_active=False, policy_allows_write_readiness=True)

    assert payload["ok"] is False
    assert payload["error_code"] == "UNLOCK_DENIED_DISCONNECTED"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_unlock_denied_when_stale_with_zero_writes():
    payload = _unlock(connected=True, stale=True, reconciled=True, emergency_active=False, policy_allows_write_readiness=True)

    assert payload["ok"] is False
    assert payload["error_code"] == "UNLOCK_DENIED_STALE"
    assert payload["osc_writes_sent"] == 0


def test_unlock_denied_when_unreconciled_with_zero_writes():
    payload = _unlock(connected=True, stale=False, reconciled=False, emergency_active=False, policy_allows_write_readiness=True)

    assert payload["ok"] is False
    assert payload["error_code"] == "UNLOCK_DENIED_UNRECONCILED"
    assert payload["osc_writes_sent"] == 0


def test_unlock_denied_when_emergency_active_with_zero_writes():
    payload = _unlock(connected=True, stale=False, reconciled=True, emergency_active=True, policy_allows_write_readiness=True)

    assert payload["ok"] is False
    assert payload["error_code"] == "UNLOCK_DENIED_EMERGENCY"
    assert payload["osc_writes_sent"] == 0


def test_unlock_denied_when_policy_blocked_with_zero_writes():
    payload = _unlock(connected=True, stale=False, reconciled=True, emergency_active=False, policy_allows_write_readiness=False)

    assert payload["ok"] is False
    assert payload["error_code"] == "UNLOCK_DENIED_POLICY"
    assert payload["osc_writes_sent"] == 0
