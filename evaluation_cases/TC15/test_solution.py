import pytest
from .solution import calculate_refund
@pytest.mark.parametrize("total,used,days,expected", [
(100,0,10,100), (100,5,10,50), (100,10,10,0),
(200,2,4,100), (50,1,2,25), (120,3,6,60),
(1000,1,10,900), (80,4,8,40)
])
def test_refund(total,used,days,expected):
    assert calculate_refund(total,used,days) == pytest.approx(expected)

