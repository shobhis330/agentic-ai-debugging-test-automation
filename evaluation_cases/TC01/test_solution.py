import pytest
from .solution import calculate_average

def test_normal_average():
    assert calculate_average([2, 4, 6, 8]) == 5.0

def test_single_element():
    assert calculate_average([10]) == 10

def test_negative_numbers():
    assert calculate_average([-2, -4, -6]) == -4

def test_empty_list():
    with pytest.raises(ValueError):
        calculate_average([])

