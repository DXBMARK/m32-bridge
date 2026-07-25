from datetime import UTC, datetime, timedelta

from m32_bridge.state.snapshot import build_snapshot


def test_snapshot_checksum_and_partial_labeling():
    now = datetime.now(UTC)
    snapshot = build_snapshot(
        snapshot_id="snap_12345678",
        identity={"target_kind": "fake_m32", "model": "M32", "hardware_verified": False},
        firmware={"version": "4.13", "status": "known"},
        environment_label="emulator",
        state_values=[
            {
                "path": "/ch/01/mix/fader",
                "raw_value": 0.5,
                "native_value": -6,
                "display_value": "-6.0 dB",
                "unit": "dB",
                "revision": 1,
                "observed_at": now.isoformat(),
                "fresh_until": (now + timedelta(seconds=1)).isoformat(),
                "source": "fake_m32",
                "support_status": "supported",
                "environment_label": "emulator",
            }
        ],
        missing_paths=["/node/missing"],
    )
    assert snapshot["checksum"].startswith("sha256:")
    assert snapshot["complete"] is False

