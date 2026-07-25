from __future__ import annotations

from m32_bridge.diagnostics.preflight import run_event_preflight
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.analysis_tools import m32_recommend_event_setup
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _event_profile(*, defined: bool = True) -> dict[str, object]:
    measurement_microphone = (
        {
            "defined": True,
            "channel": 32,
            "role": "measurement_microphone",
            "phantom_policy": "manual_only",
        }
        if defined
        else {
            "defined": False,
            "channel": None,
            "role": None,
            "phantom_policy": "manual_only",
        }
    )
    return {
        "schema_version": "1.0.0",
        "event_profile_id": "event_measurement_test",
        "name": "Measurement microphone integration profile",
        "created_at": "2026-07-20T00:00:00Z",
        "channel_dictionary": [
            {"id": 1, "role": "vocal", "label": "Measurement-looking channel name", "phantom_policy": "manual_only", "protected": False},
            {"id": 32, "role": "measurement_microphone", "label": "RTA Reference", "phantom_policy": "manual_only", "protected": True},
        ],
        "bus_dictionary": [
            {"id": 1, "role": "monitor_mix", "label": "Wedge", "phantom_policy": "not_applicable", "protected": True}
        ],
        "output_dictionary": [
            {"id": 1, "role": "main_lr", "label": "Main LR", "phantom_policy": "not_applicable", "protected": True}
        ],
        "expected_topology": {
            "main_paths": ["LR"],
            "aes50_required": ["A"],
            "expansion_card_required": False,
        },
        "measurement_microphone": measurement_microphone,
        "protected_paths": ["/main/st", "/ch/32/mix", "/ch/32/mix/01/level"],
        "mode_permissions": {
            "OBSERVE": {"max_risk": "R0", "writes_allowed": False},
            "SOUNDCHECK": {"max_risk": "R3", "writes_allowed": True},
            "LIVE": {"max_risk": "R2", "writes_allowed": True},
            "EMERGENCY": {"max_risk": "R0", "writes_allowed": False},
        },
        "known_good_reference": {
            "snapshot_id": "snap_measurement_test",
            "checksum": "sha256:" + "a" * 64,
        },
    }


def test_measurement_microphone_deferred_profile_does_not_guess_or_write():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = run_event_preflight(client, event_profile=_event_profile(defined=False))
        data = result.to_dict()

        assert any(f["category"] == "measurement_microphone" and f["evidence"]["defined"] is False for f in data["findings"])
        assert all("/ch/01" not in path for f in data["findings"] for path in f["affected_paths"] if f["category"] == "measurement_microphone")
        assert data["proposal_created"] is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_measurement_microphone_explicit_role_checks_main_protected_sends_and_rta():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = run_event_preflight(client, event_profile=_event_profile(defined=True))
        data = result.to_dict()

        measurement_findings = [f for f in data["findings"] if f["category"] == "measurement_microphone"]
        assert measurement_findings
        assert any(f["evidence"]["channel"] == 32 for f in measurement_findings)
        assert any("main_excluded" in f["evidence"] for f in measurement_findings)
        assert any("protected_sends_checked" in f["evidence"] for f in measurement_findings)
        assert any("rta_eligible" in f["evidence"] for f in measurement_findings)
        assert data["proposal_created"] is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_measurement_microphone_phantom_advice_is_manual_and_non_executable():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        profile = _event_profile(defined=True)
        profile["measurement_microphone"]["phantom_policy"] = "forbidden"
        preflight = run_event_preflight(client, event_profile=profile).to_dict()
        recommendation = m32_recommend_event_setup(client, event_profile=profile)

        assert any("phantom" in f["summary"].lower() for f in preflight["findings"])
        assert recommendation["proposal_created"] is False
        assert recommendation["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()
