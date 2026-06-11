"""TOML codec: stdlib tomllib (tomli on 3.9/3.10) reader, own writer.

TOML datetimes/dates/times are normalized to ISO 8601 strings on load so jq
programs only ever see the JSON data model.
"""
from __future__ import annotations

import datetime
import json
import re

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

__all__ = ["TomlError", "load_all", "dump_all"]


class TomlError(ValueError):
    """Raised for TOML pureyq cannot read or write."""


def _norm(v):
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    return v


def load_all(text):
    if text.startswith("﻿"):  # tolerate a UTF-8 BOM
        text = text[1:]
    try:
        return [_norm(tomllib.loads(text))]
    except tomllib.TOMLDecodeError as e:
        raise TomlError("invalid TOML: %s" % e) from None


# --- writer ------------------------------------------------------------------

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def _key(k):
    return k if _BARE_KEY.fullmatch(k) else json.dumps(k, ensure_ascii=False)


def _path(parts):
    return ".".join(_key(p) for p in parts)


def _scalar(v):
    if v is None:
        raise TomlError("TOML cannot represent null")
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return "nan"
        if v == float("inf"):
            return "inf"
        if v == float("-inf"):
            return "-inf"
        r = repr(v)
        return r if "." in r or "e" in r or "E" in r else r + ".0"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    raise TomlError("cannot serialize %s to TOML" % type(v).__name__)


def _inline(v):
    if isinstance(v, dict):
        if not v:
            return "{}"
        return "{ %s }" % ", ".join(
            "%s = %s" % (_key(k), _inline(x)) for k, x in v.items())
    if isinstance(v, list):
        return "[%s]" % ", ".join(_inline(x) for x in v)
    return _scalar(v)


def _is_array_of_tables(v):
    return isinstance(v, list) and v and all(isinstance(x, dict) for x in v)


def _emit_table(out, table, path):
    subtables = []
    table_arrays = []
    for k, v in table.items():
        if isinstance(v, dict):
            subtables.append((k, v))
        elif _is_array_of_tables(v):
            table_arrays.append((k, v))
        else:
            out.append("%s = %s" % (_key(k), _inline(v)))
    for k, v in subtables:
        out.append("")
        out.append("[%s]" % _path(path + [k]))
        _emit_table(out, v, path + [k])
    for k, items in table_arrays:
        for item in items:
            out.append("")
            out.append("[[%s]]" % _path(path + [k]))
            _emit_table(out, item, path + [k])


def dump_all(values, indent=2, compact=False):
    values = list(values)
    if len(values) != 1:
        raise TomlError(
            "TOML output requires exactly one result, got %d" % len(values))
    root = values[0]
    if not isinstance(root, dict):
        raise TomlError("TOML output requires an object at the top level, "
                        "got %s" % type(root).__name__)
    out = []
    _emit_table(out, root, [])
    text = "\n".join(out).lstrip("\n")
    return text + "\n" if text else ""
