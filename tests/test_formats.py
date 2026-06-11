"""TOML/XML/CSV codec behavior and round trips."""
import pytest

from pureyq.formats import csvfmt, tomlfmt, xmlfmt


# --- TOML --------------------------------------------------------------------

def toml_roundtrip(doc):
    assert tomlfmt.load_all(tomlfmt.dump_all([doc]))[0] == doc


def test_toml_roundtrip_nested():
    toml_roundtrip({
        "title": "demo",
        "server": {"host": "a", "ports": [1, 2], "empty": {}},
        "points": [{"x": 1}, {"x": 2, "tags": {"a": "b"}}],
        "deep": {"a": {"b": {"c": 1}}},
    })


def test_toml_roundtrip_tricky_values():
    toml_roundtrip({
        "f": 1.5, "g": 1e100, "whole": 3.0, "neg": -2,
        "s": "line\nbreak \"quoted\"", "u": "中文",
        "mixed": [1, "x", [2]], "almost_tables": [{"a": 1}, 2],
        "a b": {"c.d": 1},
    })


def test_toml_datetimes_become_strings():
    doc = tomlfmt.load_all(
        "d = 1979-05-27T07:32:00Z\nld = 1979-05-27\nlt = 07:32:00\n")[0]
    assert doc == {"d": "1979-05-27T07:32:00+00:00",
                   "ld": "1979-05-27", "lt": "07:32:00"}


def test_toml_null_rejected():
    with pytest.raises(tomlfmt.TomlError):
        tomlfmt.dump_all([{"a": None}])


def test_toml_needs_one_object():
    with pytest.raises(tomlfmt.TomlError):
        tomlfmt.dump_all([1])
    with pytest.raises(tomlfmt.TomlError):
        tomlfmt.dump_all([{"a": 1}, {"b": 2}])


def test_toml_invalid_input():
    with pytest.raises(tomlfmt.TomlError):
        tomlfmt.load_all("a = ")


# --- XML ---------------------------------------------------------------------

def test_xml_mapping_convention():
    xml = '<root id="1"><item>a</item><item>b</item><nested><x>1</x></nested></root>'
    doc = xmlfmt.load_all(xml)[0]
    assert doc == {"root": {"@id": "1", "item": ["a", "b"],
                            "nested": {"x": "1"}}}
    assert xmlfmt.load_all(xmlfmt.dump_all([doc]))[0] == doc


def test_xml_text_with_attributes():
    assert xmlfmt.load_all('<a href="x">link</a>')[0] == \
        {"a": {"@href": "x", "#text": "link"}}


def test_xml_empty_element():
    assert xmlfmt.load_all("<a/>")[0] == {"a": None}


def test_xml_invalid():
    with pytest.raises(ValueError):
        xmlfmt.load_all("<a><b></a>")


def test_xml_output_needs_single_root():
    with pytest.raises(ValueError):
        xmlfmt.dump_all([{"a": 1, "b": 2}])


def test_xml_numbers_and_bools_serialize():
    out = xmlfmt.dump_all([{"r": {"n": 1, "f": 1.5, "t": True}}])
    assert xmlfmt.load_all(out)[0] == {"r": {"n": "1", "f": "1.5", "t": "true"}}


# --- CSV/TSV -----------------------------------------------------------------

def test_csv_load_types():
    docs = csvfmt.load_all("name,age,zip,ok,score\nbob,30,01234,true,1.5\n")
    assert docs == [[{"name": "bob", "age": 30, "zip": "01234",
                      "ok": True, "score": 1.5}]]


def test_csv_roundtrip_and_quoting():
    doc = [{"a": 1, "b": "x,y"}, {"a": 2, "b": "line\nbreak"}]
    text = csvfmt.dump_all([doc])
    assert csvfmt.load_all(text)[0] == doc


def test_csv_header_union():
    assert csvfmt.dump_all([[{"a": 1}, {"b": 2}]]) == "a,b\n1,\n,2\n"


def test_csv_array_rows():
    assert csvfmt.dump_all([[["a", 1], ["b", 2]]]) == "a,1\nb,2\n"


def test_csv_nested_rejected():
    with pytest.raises(ValueError):
        csvfmt.dump_all([[{"a": {"b": 1}}]])


def test_tsv():
    assert csvfmt.dump_all([[{"a": 1, "b": "x"}]], delimiter="\t") == \
        "a\tb\n1\tx\n"
    assert csvfmt.load_all("a\tb\n1\tx\n", delimiter="\t") == [[{"a": 1, "b": "x"}]]


def test_csv_empty():
    assert csvfmt.load_all("") == [[]]
