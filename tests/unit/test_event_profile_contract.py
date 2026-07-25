from __future__ import annotations

from copy import deepcopy

import pytest
from jsonschema import ValidationError

from m32_bridge.config.schemas import validate_with_schema


def _known_good_profile() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "event_profile_id": "event_localtest_0001",
        "name": "Local test profile",
        "created_at": "2026-07-20T00:00:00Z",
        "channel_dictionary": [
            {"id": 1, "role": "vocal", "label": "Vocal 1", "phantom_policy": "manual_only", "protected": False},
            {"id": 32, "role": "measurement_microphone", "label": "Measurement", "phantom_policy": "manual_only", "protected": True},
        ],
        "bus_dictionary": [
            {"id": 1, "role": "monitor_mix", "label": "Monitor 1", "phantom_policy": "not_applicable", "protected": True}
        ],
        "output_dictionary": [
            {"id": 1, "role": "main_lr", "label": "Main LR", "phantom_policy": "not_applicable", "protected": True}
        ],
        "expected_topology": {
            "main_paths": ["LR"],
            "aes50_required": ["A"],
            "expansion_card_required": False,
        },
        "measurement_microphone": {
            "defined": True,
            "channel": 32,
            "role": "measurement_microphone",
            "phantom_policy": "manual_only",
        },
        "protected_paths": ["/main/st", "/bus/01", "/ch/32/mix"],
        "mode_permissions": {
            "OBSERVE": {"max_risk": "R0", "writes_allowed": False},
            "SOUNDCHECK": {"max_risk": "R3", "writes_allowed": True},
            "LIVE": {"max_risk": "R2", "writes_allowed": True},
            "EMERGENCY": {"max_risk": "R0", "writes_allowed": False},
        },
        "known_good_reference": {
            "snapshot_id": "snap_localtest_0001",
            "checksum": "sha256:" + "a" * 64,
        },
    }


def _validate(profile: dict[str, object]) -> None:
    validate_with_schema(profile, "event-profile.schema.json")


def test_known_good_event_profile_contract_covers_required_sections():
    profile = _known_good_profile()

    _validate(profile)

    assert profile["channel_dictionary"]
    assert profile["bus_dictionary"]
    assert profile["output_dictionary"]
    assert profile["protected_paths"] == ["/main/st", "/bus/01", "/ch/32/mix"]
    assert profile["mode_permissions"]["EMERGENCY"] == {"max_risk": "R0", "writes_allowed": False}
    assert profile["known_good_reference"]["snapshot_id"].startswith("snap_")


def test_deferred_measurement_microphone_allows_null_channel_and_role():
    profile = _known_good_profile()
    profile["measurement_microphone"] = {
        "defined": False,
        "channel": None,
        "role": None,
        "phantom_policy": "manual_only",
    }

    _validate(profile)


def test_defined_measurement_microphone_requires_integer_channel():
    profile = _known_good_profile()
    profile["measurement_microphone"]["channel"] = None

    with pytest.raises(ValidationError):
        _validate(profile)


@pytest.mark.parametrize("role", [None, "rta_reference", "talkback"])
def test_defined_measurement_microphone_requires_exact_role(role):
    profile = _known_good_profile()
    profile["measurement_microphone"]["role"] = role

    with pytest.raises(ValidationError):
        _validate(profile)


def test_deferred_measurement_microphone_requires_null_channel_and_role():
    profile = _known_good_profile()
    profile["measurement_microphone"] = {
        "defined": False,
        "channel": 32,
        "role": "measurement_microphone",
        "phantom_policy": "manual_only",
    }

    with pytest.raises(ValidationError):
        _validate(profile)


def test_mode_permissions_require_all_runtime_modes():
    profile = _known_good_profile()
    del profile["mode_permissions"]["EMERGENCY"]

    with pytest.raises(ValidationError):
        _validate(profile)


def test_dictionaries_reject_unknown_fields_and_invalid_ids():
    with_extra = _known_good_profile()
    with_extra["channel_dictionary"][0]["osc_path"] = "/ch/01"
    with_bad_output = deepcopy(_known_good_profile())
    with_bad_output["output_dictionary"][0]["id"] = 0

    with pytest.raises(ValidationError):
        _validate(with_extra)
    with pytest.raises(ValidationError):
        _validate(with_bad_output)

