import pytest
from .solution import reserve_stock
@pytest.mark.parametrize("stock,requested,expected", [
(10, 3, 7), (10, 10, 0), (5, 0, 5), (100, 25, 75),
(1, 1, 0), (50, 20, 30), (0, 0, 0), (8, 2, 6)
])
def test_reservation(stock, requested, expected):
    assert reserve_stock(stock, requested) == expected
def test_insufficient_stock():
    with pytest.raises(ValueError):
        reserve_stock(3, 5)

