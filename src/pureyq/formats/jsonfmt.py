"""JSON codec: stdlib parsing (orjson when available), purejq's jq-style encoder."""
from __future__ import annotations

import json

from purejq import encode, encode_pretty

try:  # optional accelerator (pip install pureyq[speed]); never required
    import orjson as _orjson
except ImportError:
    _orjson = None

__all__ = ["load_all", "dump_all"]


def load_all(text):
    """Parse a JSON document stream (concatenated values, jq-style)."""
    if _orjson is not None:
        try:
            return [_orjson.loads(text)]
        except Exception:
            pass  # multi-document stream, NaN, etc.: use the stdlib decoder
    dec = json.JSONDecoder()
    out = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            value, i = dec.raw_decode(text, i)
        except ValueError as e:
            raise ValueError("invalid JSON: %s" % e) from None
        out.append(value)
    return out


def dump_all(values, indent=2, compact=False):
    enc = encode if compact else encode_pretty
    return "".join(enc(v) + "\n" for v in values)
