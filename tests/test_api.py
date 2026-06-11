"""Public library API."""
import pureyq


def test_engine_reexports():
    assert pureyq.first(".a", {"a": 5}) == 5
    assert pureyq.all_outputs(".[]", [1, 2]) == [1, 2]
    prog = pureyq.compile(".x + 1")
    assert prog.first({"x": 1}) == 2


def test_load_dump():
    assert pureyq.load("a: 1\n") == {"a": 1}
    assert pureyq.dump({"a": 1}) == "a: 1\n"
    assert pureyq.load_all("1\n---\n2\n") == [1, 2]
    assert pureyq.dump_all([1, 2]) == "1\n---\n2\n"


def test_apply_yaml():
    out = pureyq.apply(".spec.replicas = 3", "spec:\n  replicas: 1\n")
    assert out == "spec:\n  replicas: 3\n"


def test_apply_compiled_program():
    prog = pureyq.compile(".a")
    assert pureyq.apply(prog, "a: 1\n") == "1\n"


def test_apply_multi_document():
    assert pureyq.apply(".a", "a: 1\n---\na: 2\n") == "1\n---\n2\n"


def test_apply_cross_format():
    out = pureyq.apply(".", "x = 1\n", input_format="toml",
                       output_format="json", compact=True)
    assert out == '{"x":1}\n'


def test_errors_exported():
    try:
        pureyq.compile("(((")
    except pureyq.JqParseError:
        pass
    else:
        raise AssertionError("expected JqParseError")


def test_version():
    assert pureyq.__version__
