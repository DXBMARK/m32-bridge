from hypothesis import given, strategies as st

from m32_bridge.osc.codec import pack_message, unpack_message


osc_text = st.text(
    alphabet=st.characters(blacklist_characters="\x00", blacklist_categories=("Cs",)),
    min_size=0,
    max_size=20,
)


@given(st.integers(-1000, 1000), osc_text)
def test_osc_round_trip_for_int_and_string(number, label):
    packet = pack_message("/test/path", number, label)
    message = unpack_message(packet)
    assert message.arguments == (number, label)
