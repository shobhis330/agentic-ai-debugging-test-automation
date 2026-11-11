import pytest
from .solution import validate_user_payload
@pytest.mark.parametrize("payload,expected", [
({"name":"A","email":"a@b.com","age":20},True),
({"name":"A","email":"a@b.com"},True),
({"name":"","email":"a@b.com"},False),
({"name":"A","email":"invalid"},False),
({"email":"a@b.com"},False),
({"name":"A"},False),
({"name":123,"email":"a@b.com"},False),
({"name":"A","email":"a@b.com","age":"twenty"},False)
])
def test_payload_validation(payload,expected):
    assert validate_user_payload(payload) is expected

