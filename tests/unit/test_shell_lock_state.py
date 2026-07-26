from __future__ import annotations


def test_shell_lock_sets_local_write_lock_without_osc_writes():
    from m32_bridge.interactive_shell import LocalShellState, dispatch_slash_command

    state = LocalShellState(write_locked=False)
    payload = dispatch_slash_command("/lock", shell_state=state)

    assert payload["ok"] is True
    assert payload["status"] == "LOCKED"
    assert state.write_locked is True
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_shell_unlock_affects_local_lock_state_only_when_governance_allows():
    from m32_bridge.interactive_shell import LocalShellState, dispatch_slash_command

    state = LocalShellState(write_locked=True)
    payload = dispatch_slash_command(
        "/unlock",
        shell_state=state,
        connected=True,
        stale=False,
        reconciled=True,
        emergency_active=False,
        policy_allows_write_readiness=True,
    )

    assert payload["ok"] is True
    assert payload["status"] == "UNLOCKED"
    assert state.write_locked is False
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
