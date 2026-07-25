from m32_bridge.core.proposals import digest_payload


def test_digest_is_key_order_stable_and_value_sensitive():
    assert digest_payload({"a": 1, "b": 2}) == digest_payload({"b": 2, "a": 1})
    assert digest_payload({"a": 1, "b": 2}) != digest_payload({"a": 1, "b": 3})

