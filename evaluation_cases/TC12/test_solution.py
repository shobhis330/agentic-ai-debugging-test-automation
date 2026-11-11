import pytest
from .solution import calculate_commission
@pytest.mark.parametrize("sales,rate,expected", [
(1000,5,50), (2000,10,200), (0,5,0), (500,2,10),
(100,0,0), (2500,4,100), (10000,1,100), (80,12.5,10)
])
def test_commission(sales,rate,expected):
    assert calculate_commission(sales,rate) == pytest.approx(expected)

