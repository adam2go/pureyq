"""YAML 1.2 Core Schema conformance: the footguns PyYAML's 1.1 gets wrong."""
import math

import pytest

from pureyq.formats import yaml12

LOAD_CASES = [
    ("null", None), ("~", None), ("NULL", None),
    ("true", True), ("TRUE", True), ("False", False),
    # YAML 1.1 booleans must stay strings in 1.2 (the Norway problem)
    ("no", "no"), ("yes", "yes"), ("on", "on"), ("Off", "Off"),
    ("y", "y"), ("n", "n"),
    ("42", 42), ("-7", -7), ("+5", 5),
    ("0x1A", 26), ("0o17", 15),
    ("010", 10),                    # decimal in 1.2; octal in 1.1
    ("1:30", "1:30"),               # sexagesimal 90 in 1.1
    ("2026-06-11", "2026-06-11"),   # datetime object in 1.1
    ("1_000", "1_000"),             # underscored numbers are 1.1-only
    ("1e3", 1000.0), (".5", 0.5), ("1.", 1.0),
]


@pytest.mark.parametrize("text,expected", LOAD_CASES)
def test_load_scalar(text, expected):
    assert yaml12.load("key: %s" % text) == {"key": expected}


def test_inf_nan():
    assert yaml12.load(".inf") == math.inf
    assert yaml12.load("-.Inf") == -math.inf
    assert math.isnan(yaml12.load(".NaN"))


def test_empty_stream():
    assert yaml12.load("") is None
    assert yaml12.load_all("") == []


def test_multi_document():
    assert yaml12.load_all("a: 1\n---\nb: 2\n") == [{"a": 1}, {"b": 2}]
    with pytest.raises(yaml12.YamlError):
        yaml12.load("a: 1\n---\nb: 2\n")


def test_merge_keys_still_work():
    text = "base: &b\n  x: 1\n  y: 2\nchild:\n  <<: *b\n  y: 3\n"
    assert yaml12.load(text)["child"] == {"x": 1, "y": 3}


def test_non_string_keys_stringified():
    assert yaml12.load("1: a\ntrue: b\nnull: c\n") == \
        {"1": "a", "true": "b", "null": "c"}


def test_invalid_yaml_raises():
    with pytest.raises(yaml12.YamlError):
        yaml12.load("a: [1, 2")


@pytest.mark.parametrize("s", [
    "no", "yes", "on", "true", "TRUE", "null", "~",
    "42", "010", "0x1A", "1:30", "1_000", "1e3", ".inf",
    "2026-06-11", "2026-06-11 09:14:00", "<<", "=",
])
def test_dump_quotes_ambiguous_strings(s):
    assert yaml12.dump(s) == "'%s'\n" % s
    assert yaml12.load(yaml12.dump(s)) == s


def test_dump_plain_strings_stay_plain():
    assert yaml12.dump("hello") == "hello\n"
    assert yaml12.dump("hello world") == "hello world\n"


def test_dump_key_order_preserved():
    assert yaml12.dump({"b": 1, "a": 2}) == "b: 1\na: 2\n"


def test_dump_no_anchors_for_shared_objects():
    shared = {"k": 1}
    out = yaml12.dump({"a": shared, "b": shared})
    assert "&" not in out and "*" not in out
    assert yaml12.load(out) == {"a": {"k": 1}, "b": {"k": 1}}


def test_roundtrip():
    value = {"a": [1, 2.5, None, True, "no"], "b": {"c": "x"},
             "中文": "✓", "list": [{"deep": [[]]}]}
    assert yaml12.load(yaml12.dump(value)) == value


def test_dump_all_separators():
    assert yaml12.dump_all([{"a": 1}, {"b": 2}]) == "a: 1\n---\nb: 2\n"


def test_explicit_11_tags_mapped_to_json_model():
    assert yaml12.load("!!timestamp 2001-12-15") == "2001-12-15"
    assert yaml12.load("!!set {a, b}") == {"a": None, "b": None}


def test_pure_and_c_paths_agree():
    """The libyaml fast path must match the pure Python fallback exactly."""
    import yaml as pyyaml
    text = ("a: no\nb: 010\nc: 2026-06-11\nd: 0x1A\ne: [.inf, 1e3, '1:30']\n"
            "1: x\ntrue: y\nf: {sub: [~, TRUE, off]}\n")
    pure = pyyaml.load(text, Loader=yaml12.CoreLoader)
    fast = pyyaml.load(text, Loader=yaml12.Loader)
    assert pure == fast
    kw = dict(sort_keys=False, default_flow_style=False, allow_unicode=True)
    assert (pyyaml.dump(pure, Dumper=yaml12.CoreDumper, **kw)
            == pyyaml.dump(fast, Dumper=yaml12.Dumper, **kw))
