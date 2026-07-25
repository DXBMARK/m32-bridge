from datetime import UTC, datetime, timedelta

from m32_bridge.core.models import StateValue
from m32_bridge.state.cache import StateCache


def _value(path="/ch/01/mix/fader", revision=1):
    now = datetime.now(UTC)
    return StateValue(path, 0.5, -6.0, "-6.0 dB", "dB", "float", "fake_m32", revision, now, now + timedelta(seconds=1), 1.0, False, False, "supported", "emulator")


def test_state_cache_rejects_out_of_order_revision_and_detects_manual_change():
    cache = StateCache()
    first = cache.apply(_value(revision=2), change_source="console")
    old = cache.apply(_value(revision=1), change_source="console")
    manual = cache.apply(_value(revision=3), change_source="console")
    assert first.revision == 2
    assert old.change_source == "duplicate_or_out_of_order"
    assert manual.manual_change_detected

