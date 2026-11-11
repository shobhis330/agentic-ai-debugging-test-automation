import pytest
from .solution import calculate_shipping
@pytest.mark.parametrize("weight,zone,expected", [
(1,"local",5), (2,"local",10), (1,"regional",8),
(2,"regional",16), (1,"national",12), (0,"local",0),
(3,"local",15), (2,"national",24)
])
def test_shipping(weight,zone,expected):
    assert calculate_shipping(weight,zone) == expected

