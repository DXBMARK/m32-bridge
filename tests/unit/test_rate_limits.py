from datetime import UTC, datetime, timedelta

from m32_bridge.core.rate_limits import RateLimiter, live_fader_delta_allowed


def test_rate_limiter_serializes_per_resource():
    now = datetime.now(UTC)
    limiter = RateLimiter(min_interval_ms=500)
    assert limiter.allow("/ch/01/mix/fader", now)
    assert not limiter.allow("/ch/01/mix/fader", now + timedelta(milliseconds=100))
    assert limiter.allow("/ch/01/mix/fader", now + timedelta(milliseconds=600))


def test_live_fader_delta_limit():
    assert live_fader_delta_allowed(-6.0, -3.0)
    assert not live_fader_delta_allowed(-6.0, -2.5)


def test_proposal_per_resource_limit_uses_same_resource_key():
    now = datetime.now(UTC)
    limiter = RateLimiter(min_interval_ms=1000)
    assert limiter.allow("/ch/01/mix/fader", now)
    assert not limiter.allow("/ch/01/mix/fader", now + timedelta(milliseconds=999))
    assert limiter.allow("/ch/02/mix/fader", now + timedelta(milliseconds=100))
