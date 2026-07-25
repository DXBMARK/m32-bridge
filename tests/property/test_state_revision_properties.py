from datetime import UTC, datetime, timedelta

from hypothesis import given, strategies as st

from m32_bridge.core.models import StateValue
from m32_bridge.state.cache import StateCache


@given(st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=25))
def test_cache_revision_never_decreases(revisions):
    cache = StateCache()
    now = datetime.now(UTC)
    for revision in revisions:
        value = StateValue("/ch/01/mix/fader", revision, revision, str(revision), None, "int", "fake_m32", revision, now, now + timedelta(seconds=1), 1.0, False, False, "supported", "emulator")
        cache.apply(value)
    assert cache.revisions["/ch/01/mix/fader"] == max(revisions)

