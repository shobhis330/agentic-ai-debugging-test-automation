import pytest
from .solution import parse_csv_row
@pytest.mark.parametrize("line,expected", [
("a,b,c",["a","b","c"]), ('1,"New York",3',["1","New York","3"]),
('"Doe, Jane",30,NY',["Doe, Jane","30","NY"]),
("one,two",["one","two"]), ("",[]),
('"a,b","c,d"',["a,b","c,d"]),
("x,y,z,w",["x","y","z","w"]),
('"hello, world",42',["hello, world","42"])
])
def test_csv_parsing(line,expected):
    assert parse_csv_row(line) == expected

