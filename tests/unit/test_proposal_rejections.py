import pytest

from m32_bridge.core.models import RuntimeMode
from m32_bridge.mcp.write_tools import m32_propose_changes


def test_rejects_raw_osc_arbitrary_paths_r4_main_and_r3_outside_soundcheck():
    with pytest.raises(ValueError):
        m32_propose_changes(intent="raw", targets=[{"semantic_action": "raw_osc", "target_path": "/raw/osc", "before_value": 0, "requested_value": 1}])
    with pytest.raises(ValueError):
        m32_propose_changes(intent="phantom", targets=[{"semantic_action": "phantom_enable", "target_path": "/headamp/001/phantom", "before_value": False, "requested_value": True}])
    with pytest.raises(ValueError):
        m32_propose_changes(intent="main", targets=[{"semantic_action": "fader_set", "target_path": "/main/st/mix/fader", "before_value": -10.0, "requested_value": -8.0}])
    with pytest.raises(ValueError):
        m32_propose_changes(
            intent="headamp live",
            runtime_mode=RuntimeMode.LIVE,
            targets=[{"semantic_action": "headamp_set", "target_path": "/headamp/001/gain", "target_kind": "headamp", "before_value": 10.0, "requested_value": 6.0}],
        )

