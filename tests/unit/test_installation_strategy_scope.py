from __future__ import annotations


def test_installation_strategy_is_future_only_and_does_not_enable_packaging():
    from m32_bridge.diagnostics.os_recommendations import future_installation_strategy

    payload = future_installation_strategy()

    assert payload["current_strategy"] == "development_or_user_local_launcher"
    assert payload["packaging_implemented"] is False
    assert payload["installer_created"] is False
    assert payload["remote_mcp_implemented"] is False
    assert payload["chatgpt_tunnel_implemented"] is False
    assert payload["webui_added"] is False
    assert payload["database_added"] is False
    assert payload["osc_writes_sent"] == 0


def test_future_packaging_notes_are_documentation_only():
    from m32_bridge.diagnostics.os_recommendations import future_installation_strategy

    payload = future_installation_strategy()
    notes = " ".join(payload["future_packaging_notes"]).lower()

    assert "future os packages" in notes
    assert "future raspberry pi" in notes
    assert "future mcp extension" in notes
    assert "future portable kit" in notes
    assert "implemented" not in notes
