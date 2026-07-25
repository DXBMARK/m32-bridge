import pytest

from m32_bridge.osc.codec import OscCodecError, format_db, pack_message, quantize_to_grid, unpack_message


def test_pack_unpack_supported_types_round_trip():
    packet = pack_message("/ch/01/mix/fader", 1, 0.5, "label", b"abc", True, False)
    message = unpack_message(packet)
    assert message.address == "/ch/01/mix/fader"
    assert message.arguments[0] == 1
    assert message.arguments[2] == "label"
    assert message.arguments[3] == b"abc"
    assert message.arguments[4:] == (True, False)


def test_rejects_malformed_packet():
    with pytest.raises(OscCodecError):
        unpack_message(b"/bad")


def test_value_grid_and_display_format():
    assert quantize_to_grid(5.96, 0.5) == 6.0
    assert format_db(6.0) == "+6.0 dB"

