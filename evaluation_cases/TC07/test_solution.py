import pytest
from .solution import paginate
@pytest.mark.parametrize("items,page,size,expected", [
(list(range(1,11)),1,3,[1,2,3]), (list(range(1,11)),2,3,[4,5,6]),
(list(range(1,11)),4,3,[10]), (list(range(1,6)),1,5,[1,2,3,4,5]),
([],1,10,[]), ([1,2,3],2,2,[3]), ([1,2],1,1,[1]),
(list(range(8)),3,3,[6,7])
])
def test_pagination(items,page,size,expected):
    assert paginate(items,page,size) == expected

