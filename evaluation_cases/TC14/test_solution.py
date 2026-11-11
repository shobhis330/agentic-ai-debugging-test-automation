import pytest
from .solution import calculate_average_latency
@pytest.mark.parametrize("values,expected", [
([10,20,30],20), ([5],5), ([0,0,0],0),
([100,200],150), ([10,20,30,40],25),
([1,3,5,7,9],5), ([50,100,150],100),
([2,4],3)
])
def test_latency_average(values,expected):
    assert calculate_average_latency(values) == pytest.approx(expected)

