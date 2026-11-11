import pytest
from .solution import calculate_retry_delay
@pytest.mark.parametrize("attempt,base,maximum,expected", [
(0,2,30,2), (1,2,30,2), (2,2,30,4), (3,2,30,8),
(4,2,30,16), (5,2,30,30), (6,2,30,30), (2,3,20,6)
])
def test_retry_backoff(attempt,base,maximum,expected):
    assert calculate_retry_delay(attempt,base,maximum) == expected

