from hypothesis import given, strategies as st

from m32_bridge.osc.codec import quantize_to_grid


@given(st.floats(min_value=-90, max_value=10, allow_nan=False, allow_infinity=False))
def test_quantized_value_lands_on_half_db_grid(value):
    quantized = quantize_to_grid(value, 0.5)
    assert abs((quantized * 2) - round(quantized * 2)) < 1e-6

