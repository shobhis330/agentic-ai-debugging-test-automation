from .solution import is_adult

def test_adult_age():
    assert is_adult(25) is True

def test_exactly_18():
    assert is_adult(18) is True

def test_under_18():
    assert is_adult(17) is False

