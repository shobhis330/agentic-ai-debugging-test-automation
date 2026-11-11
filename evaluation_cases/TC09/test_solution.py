import pytest
from .solution import normalize_email
@pytest.mark.parametrize("email,expected", [
("USER@example.com","user@example.com"),
(" User@Example.COM ","user@example.com"),
("Admin@COMPANY.IN","admin@company.in"),
("a.b@domain.org","a.b@domain.org"),
("TEST@MAIL.COM","test@mail.com"),
(" hello@world.net ","hello@world.net"),
("X@Y.COM","x@y.com"), ("name@EXAMPLE.COM","name@example.com")
])
def test_email_normalization(email,expected):
    assert normalize_email(email) == expected

