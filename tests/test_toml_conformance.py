"""Official toml-test suite (vendored TOML 1.0 subset) against the TOML codec.

Valid cases must parse and match the typed-JSON expectation; invalid cases
must be rejected. pureyq normalizes TOML datetimes to ISO 8601 strings, so
datetime expectations are compared after parsing both sides.
"""
import datetime
import json
import math
import re
from pathlib import Path

import pytest

from pureyq.formats import tomlfmt

ROOT = Path(__file__).parent / "conformance" / "toml-test"
_CASES = [line for line in
          (ROOT / "files-toml-1.0.0").read_text().splitlines()
          if line.endswith(".toml")]
VALID = [c for c in _CASES if c.startswith("valid/")]
INVALID = [c for c in _CASES if c.startswith("invalid/")]


def _read(case):
    # newline="" keeps bare \r intact: TOML must reject it, and universal
    # newlines would silently rewrite it to \n before the parser sees it.
    with open(ROOT / case, encoding="utf-8", newline="") as f:
        return f.read()

_FRACTION = re.compile(r"\.(\d+)")


def _norm_dt(s, kind):
    # Normalize fractional seconds to 6 digits so 3.9's fromisoformat copes.
    s = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"),
                      s.replace("Z", "+00:00").replace("z", "+00:00"))
    if kind in ("datetime", "datetime-local"):
        return datetime.datetime.fromisoformat(
            s.replace("t", "T").replace(" ", "T"))
    if kind == "date-local":
        return datetime.date.fromisoformat(s)
    return datetime.time.fromisoformat(s)


def _float(v):
    low = v.lower().lstrip("+")
    if low in ("inf", "-inf"):
        return float(low)
    if low in ("nan", "-nan"):
        return float("nan")
    return float(v)


def _eq(exp, got):
    if isinstance(exp, dict) and set(exp) == {"type", "value"}:
        t, v = exp["type"], exp["value"]
        if t == "integer":
            return (isinstance(got, int) and not isinstance(got, bool)
                    and got == int(v))
        if t == "float":
            if not isinstance(got, float):
                return False
            f = _float(v)
            return math.isnan(got) if math.isnan(f) else got == f
        if t == "bool":
            return isinstance(got, bool) and got == (v == "true")
        if t == "string":
            return isinstance(got, str) and got == v
        if t in ("datetime", "datetime-local", "date-local", "time-local"):
            return isinstance(got, str) and _norm_dt(got, t) == _norm_dt(v, t)
        raise AssertionError("unknown toml-test type: %s" % t)
    if isinstance(exp, list):
        return (isinstance(got, list) and len(exp) == len(got)
                and all(map(_eq, exp, got)))
    if isinstance(exp, dict):
        return (isinstance(got, dict) and set(exp) == set(got)
                and all(_eq(v, got[k]) for k, v in exp.items()))
    raise AssertionError("unexpected expectation node: %r" % (exp,))


@pytest.mark.parametrize("case", VALID)
def test_valid(case):
    doc = tomlfmt.load_all(_read(case))[0]
    expected = json.loads(
        (ROOT / case).with_suffix(".json").read_text(encoding="utf-8"))
    assert _eq(expected, doc), "parsed value does not match expectation"


@pytest.mark.parametrize("case", INVALID)
def test_invalid(case):
    try:
        text = _read(case)
    except UnicodeDecodeError:
        return  # rejected before the parser, same outcome as the CLI
    with pytest.raises(tomlfmt.TomlError):
        tomlfmt.load_all(text)
