"""CSV/TSV codec: first row is the header; a document is an array of objects.

Cell values are typed on load the way yq does it: integers, floats and
true/false are parsed (leading-zero numbers like ZIP codes stay strings),
everything else stays a string.
"""
from __future__ import annotations

import csv
import io
import re

__all__ = ["load_all", "dump_all"]

_NUM = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")


def _infer(s):
    if s == "true":
        return True
    if s == "false":
        return False
    if _NUM.fullmatch(s):
        return float(s) if "." in s or "e" in s or "E" in s else int(s)
    return s


def load_all(text, delimiter=","):
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    except csv.Error as e:
        raise ValueError("invalid CSV: %s" % e) from None
    if not rows:
        return [[]]
    header = rows[0]
    return [[{h: _infer(c) for h, c in zip(header, row)} for row in rows[1:]]]


def _cell(v):
    if v is None:
        return ""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (dict, list)):
        raise ValueError("CSV cannot represent nested structures; "
                         "flatten the data first")
    return str(v)


def dump_all(values, indent=2, compact=False, delimiter=","):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    for doc in values:
        if not isinstance(doc, list):
            raise ValueError("CSV output requires an array, got %s"
                             % type(doc).__name__)
        if doc and all(isinstance(r, dict) for r in doc):
            header = []
            for row in doc:
                for k in row:
                    if k not in header:
                        header.append(k)
            w.writerow(header)
            for row in doc:
                w.writerow([_cell(row.get(k)) for k in header])
        else:
            for row in doc:
                w.writerow([_cell(c) for c in row]
                           if isinstance(row, list) else [_cell(row)])
    return buf.getvalue()
