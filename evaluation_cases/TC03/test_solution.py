from .solution import calculate_total

def test_normal_total():
    assert calculate_total([10, 20, 30]) == 60

def test_single_price():
    assert calculate_total([15]) == 15

def test_empty_prices():
    assert calculate_total([]) == 0

