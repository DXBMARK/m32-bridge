from m32_bridge.core.models import RiskClass, RuntimeMode
from m32_bridge.core.policy import PolicyRequest, evaluate_policy


def test_emergency_blocks_all_writes_including_mute_and_rollback():
    decision = evaluate_policy(PolicyRequest(RuntimeMode.EMERGENCY, RiskClass.R1, "mute_set", "/ch/01/mix/on"))
    assert not decision.allowed
    assert "EMERGENCY_LOCKED" in decision.reasons


def test_r3_soundcheck_only_and_requires_snapshot():
    live = evaluate_policy(PolicyRequest(RuntimeMode.LIVE, RiskClass.R3, "headamp_set", "/headamp/001/gain", has_snapshot=True))
    assert "R3_MODE_DENIED" in live.reasons
    soundcheck = evaluate_policy(PolicyRequest(RuntimeMode.SOUNDCHECK, RiskClass.R3, "headamp_set", "/headamp/001/gain", has_snapshot=True))
    assert soundcheck.allowed


def test_r4_and_main_are_blocked():
    r4 = evaluate_policy(PolicyRequest(RuntimeMode.SOUNDCHECK, RiskClass.R4, "phantom_enable", "/headamp/001/phantom"))
    main = evaluate_policy(PolicyRequest(RuntimeMode.SOUNDCHECK, RiskClass.R1, "fader_set", "/main/st/mix/fader", affects_main=True))
    assert "R4_BLOCKED" in r4.reasons
    assert "MAIN_PROTECTED" in main.reasons

