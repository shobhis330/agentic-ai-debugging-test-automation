import pytest
from .solution import calculate_invoice
@pytest.mark.parametrize("subtotal,rate,discount,expected", [
(100, .10, 0, 110), (200, .05, 0, 210),
(100, .10, 10, 100), (500, .18, 50, 540),
(0, .10, 0, 0), (80, 0, 0, 80),
(1000, .10, 100, 1000), (50, .20, 5, 55)
])
def test_invoice(subtotal, rate, discount, expected):
    assert calculate_invoice(subtotal, rate, discount) == pytest.approx(expected)

