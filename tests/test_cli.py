"""End-to-end CLI behavior through pureyq.cli.main()."""
import io

import pytest

from pureyq.cli import main


@pytest.fixture
def run(monkeypatch, capsys):
    def _run(argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        code = main(argv)
        out, err = capsys.readouterr()
        return code, out, err
    return _run


def test_yaml_in_yaml_out_default(run):
    code, out, err = run([".a"], stdin="a:\n  b: 1\n")
    assert (code, out) == (0, "b: 1\n")


def test_string_results_unquoted_only_with_r(run):
    assert run([".a"], stdin="a: hello\n")[1] == "hello\n"
    assert run([".a"], stdin="a: 'no'\n")[1] == "'no'\n"
    assert run(["-r", ".a"], stdin="a: 'no'\n")[1] == "no\n"


def test_output_json(run):
    code, out, _ = run(["-o", "json", "-c", "."], stdin="a: 1\nb: [x, y]\n")
    assert (code, out) == (0, '{"a":1,"b":["x","y"]}\n')


def test_multi_document_stream(run):
    code, out, _ = run([".a"], stdin="a: 1\n---\na: 2\n")
    assert (code, out) == (0, "1\n---\n2\n")


def test_slurp(run):
    code, out, _ = run(["-s", "-o", "json", "-c", "."],
                       stdin="a: 1\n---\na: 2\n")
    assert (code, out) == (0, '[{"a":1},{"a":2}]\n')


def test_null_input_and_args(run):
    assert run(["-n", "-o", "json", "-c", "{x: 1}"])[1] == '{"x":1}\n'
    assert run(["-n", "-r", "--arg", "name", "bob", "$name"])[1] == "bob\n"


def test_csv_stdin(run):
    code, out, _ = run(["-p", "csv", "-o", "json", "-c", "."],
                       stdin="a,b\n1,x\n")
    assert (code, out) == (0, '[{"a":1,"b":"x"}]\n')


def test_file_extension_detection(run, tmp_path):
    f = tmp_path / "conf.toml"
    f.write_text('[server]\nport = 8080\n')
    code, out, _ = run([".server.port", "-o", "json", str(f)])
    assert (code, out) == (0, "8080\n")
    # default output format follows the input: TOML in, TOML out
    code, out, _ = run([".server.port = 9090", str(f)])
    assert (code, out) == (0, "[server]\nport = 9090\n")


def test_in_place_edit(run, tmp_path):
    f = tmp_path / "deploy.yaml"
    f.write_text("spec:\n  replicas: 1\n  image: app:v1\n")
    code, out, _ = run(["-i", ".spec.replicas = 3", str(f)])
    assert (code, out) == (0, "")
    assert f.read_text() == "spec:\n  replicas: 3\n  image: app:v1\n"


def test_in_place_multi_document(run, tmp_path):
    f = tmp_path / "all.yaml"
    f.write_text("a: 1\n---\na: 2\n")
    code, _, _ = run(["-i", ".a += 10", str(f)])
    assert code == 0
    assert f.read_text() == "a: 11\n---\na: 12\n"


def test_in_place_format_conversion(run, tmp_path):
    f = tmp_path / "conf.toml"
    f.write_text("x = 1\n")
    code, _, _ = run(["-i", "-o", "yaml", ".x = 2", str(f)])
    assert code == 0
    assert f.read_text() == "x: 2\n"


def test_in_place_requires_files(run):
    code, _, err = run(["-i", "."])
    assert code == 2 and "in-place" in err


def test_exit_codes(run):
    assert run(["((("], stdin="a: 1\n")[0] == 3      # parse error
    assert run(["."], stdin="a: [1\n")[0] == 2       # invalid input
    assert run(["-e", ".missing"], stdin="a: 1\n")[0] == 1
    assert run([".a.b"], stdin="a: 1\n")[0] == 5     # jq runtime error


def test_toml_output_single_result_only(run):
    code, _, err = run(["-o", "toml", ".a, .a"], stdin="a: {x: 1}\n")
    assert code == 5 and "TOML" in err


def test_norway_problem_end_to_end(run):
    code, out, _ = run(["-o", "json", "-c", ".country"], stdin="country: NO\n")
    assert (code, out) == (0, '"NO"\n')


def test_join_output(run):
    assert run(["-j", ".a, .b"], stdin="a: x\nb: y\n")[1] == "xy"
