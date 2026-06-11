"""Format registry: codecs keyed by name, with file-extension detection.

Every codec exposes ``load_all(text) -> [doc, ...]`` and
``dump_all(values, indent, compact) -> str``; load errors raise ValueError.
"""
from __future__ import annotations

import os

from . import csvfmt, jsonfmt, tomlfmt, xmlfmt, yaml12

__all__ = ["FORMAT_NAMES", "detect", "load_all", "dump_all"]

FORMAT_NAMES = ("yaml", "json", "toml", "xml", "csv", "tsv")

_EXTENSIONS = {
    ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".jsonl": "json", ".ndjson": "json",
    ".toml": "toml",
    ".xml": "xml",
    ".csv": "csv",
    ".tsv": "tsv", ".tab": "tsv",
}


def detect(path, default="yaml"):
    """Pick a format from a file extension; YAML when unrecognized."""
    return _EXTENSIONS.get(os.path.splitext(path)[1].lower(), default)


def load_all(fmt, text):
    if fmt == "yaml":
        return yaml12.load_all(text)
    if fmt == "json":
        return jsonfmt.load_all(text)
    if fmt == "toml":
        return tomlfmt.load_all(text)
    if fmt == "xml":
        return xmlfmt.load_all(text)
    if fmt == "csv":
        return csvfmt.load_all(text)
    if fmt == "tsv":
        return csvfmt.load_all(text, delimiter="\t")
    raise ValueError("unknown input format: %s" % fmt)


def dump_all(fmt, values, indent=2, compact=False):
    if fmt == "yaml":
        return yaml12.dump_all(values, indent=indent, flow=compact)
    if fmt == "json":
        return jsonfmt.dump_all(values, indent=indent, compact=compact)
    if fmt == "toml":
        return tomlfmt.dump_all(values, indent=indent, compact=compact)
    if fmt == "xml":
        return xmlfmt.dump_all(values, indent=indent, compact=compact)
    if fmt == "csv":
        return csvfmt.dump_all(values, indent=indent, compact=compact)
    if fmt == "tsv":
        return csvfmt.dump_all(values, indent=indent, compact=compact,
                               delimiter="\t")
    raise ValueError("unknown output format: %s" % fmt)
