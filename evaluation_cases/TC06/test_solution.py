import pytest
from .solution import is_password_strong
@pytest.mark.parametrize("password,expected", [
("StrongPass123!", True), ("Abcdefgh12!X", True),
("short", False), ("alllowercase123!", False),
("ALLUPPERCASE123!", False), ("NoDigitsHere!!", False),
("NoSpecial12345", False), ("Ab1!", False)
])
def test_password_policy(password, expected):
    assert is_password_strong(password) is expected

