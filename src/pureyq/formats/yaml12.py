"""YAML codec: YAML 1.2 Core Schema on top of PyYAML's safe loader/dumper.

PyYAML implements YAML 1.1, whose implicit typing has famous footguns:
`no`/`on` become booleans (the Norway problem), `2026-06-11` becomes a
datetime object the jq engine cannot process, `1:30` becomes the integer 90
(sexagesimal), and `010` becomes 8 (octal). The loader/dumper here replace
the implicit resolvers with the YAML 1.2 Core Schema set, keeping only the
`<<` merge-key extension because real-world configs rely on it.

On output, strings that any common YAML loader (1.1 or 1.2) would read back
as a different type are single-quoted, so emitted documents are safe for
both generations of parsers.
"""
from __future__ import annotations

import json
import re

import yaml

__all__ = ["YamlError", "load", "load_all", "dump", "dump_all"]


class YamlError(ValueError):
    """Raised for YAML documents pureyq cannot read or write."""


def _norm_key(k):
    if isinstance(k, str):
        return k
    if k is True:
        return "true"
    if k is False:
        return "false"
    if k is None:
        return "null"
    if isinstance(k, tuple):
        k = list(k)
    return json.dumps(k, ensure_ascii=False)


def _parse_int(s):
    if s.startswith("0o"):
        return int(s[2:], 8)
    if s.startswith("0x"):
        return int(s[2:], 16)
    return int(s)  # leading zeros are decimal in 1.2, not octal


def _parse_float(s):
    low = s.lower()
    if low.endswith("inf"):
        return float("-inf") if s[0] == "-" else float("inf")
    if low.endswith("nan"):
        return float("nan")
    return float(s)


_SENTINEL = object()
_SCALAR_NODE = yaml.ScalarNode


def _fast_scalar(node):
    """Convert a resolved scalar node directly, skipping construct_object.

    Scalars cannot be recursive and re-constructing an aliased scalar is
    harmless (immutable values), so the constructor cache and recursion
    bookkeeping - the bulk of per-node cost on big documents - are pure
    overhead here. Returns _SENTINEL when the node needs the full path.
    """
    if node.__class__ is not _SCALAR_NODE:
        return _SENTINEL
    tag = node.tag
    if tag == "tag:yaml.org,2002:str":
        return node.value
    if tag == "tag:yaml.org,2002:int":
        return _parse_int(node.value)
    if tag == "tag:yaml.org,2002:float":
        return _parse_float(node.value)
    if tag == "tag:yaml.org,2002:bool":
        return node.value[0] in "tT"
    if tag == "tag:yaml.org,2002:null":
        return None
    return _SENTINEL


class CoreLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        # jq object keys are strings. Stringify non-string keys *while*
        # building the dict: in Python `1 == True`, so a post-pass would
        # already have lost one of the entries `1:` / `true:`.
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = _fast_scalar(key_node)
            if key is _SENTINEL:
                key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                key = _norm_key(key)
            value = _fast_scalar(value_node)
            if value is _SENTINEL:
                value = self.construct_object(value_node, deep=deep)
            mapping[key] = value
        return mapping

    def construct_sequence(self, node, deep=False):
        out = []
        for child in node.value:
            v = _fast_scalar(child)
            if v is _SENTINEL:
                v = self.construct_object(child, deep=deep)
            out.append(v)
        return out


class CoreDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        # jq outputs are trees (JSON data model); never emit &anchor/*alias.
        return True


# When PyYAML ships with libyaml (the common case for wheels), mirror the
# core-schema classes onto the C parser/emitter. Pure Python remains the
# always-available fallback, so environments like Pyodide still work.
if getattr(yaml, "__with_libyaml__", False):
    class CoreCLoader(yaml.CSafeLoader):
        construct_mapping = CoreLoader.construct_mapping
        construct_sequence = CoreLoader.construct_sequence

    class CoreCDumper(yaml.CSafeDumper):
        ignore_aliases = CoreDumper.ignore_aliases
else:  # pragma: no cover - depends on how PyYAML was built
    CoreCLoader = CoreLoader
    CoreCDumper = CoreDumper

_LOADERS = dict.fromkeys((CoreLoader, CoreCLoader))
_DUMPERS = dict.fromkeys((CoreDumper, CoreCDumper))


# --- YAML 1.2 Core Schema implicit resolvers -------------------------------

_NULL_RE = re.compile(r"^(?:~|null|Null|NULL|)$")
_BOOL_RE = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_INT_RE = re.compile(r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$")
_FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$")

for _cls in list(_LOADERS) + list(_DUMPERS):
    _cls.yaml_implicit_resolvers = {}

# Order matters where regexes overlap (plain integers also match the float
# regex): the first resolver added for a leading character wins.
for _tag, _re_, _first in [
        ("tag:yaml.org,2002:null", _NULL_RE, ["~", "n", "N", ""]),
        ("tag:yaml.org,2002:bool", _BOOL_RE, list("tTfF")),
        ("tag:yaml.org,2002:int", _INT_RE, list("-+0123456789")),
        ("tag:yaml.org,2002:float", _FLOAT_RE, list("-+0123456789.")),
]:
    for _cls in list(_LOADERS) + list(_DUMPERS):
        _cls.add_implicit_resolver(_tag, _re_, _first)

# YAML 1.2 dropped merge keys, but k8s/compose files still use them.
for _cls in _LOADERS:
    _cls.add_implicit_resolver(
        "tag:yaml.org,2002:merge", re.compile(r"^(?:<<)$"), ["<"])


# --- constructors with 1.2 semantics ----------------------------------------

def _construct_null(loader, node):
    return None


def _construct_bool(loader, node):
    return loader.construct_scalar(node)[0] in "tT"


def _construct_int(loader, node):
    return _parse_int(loader.construct_scalar(node))


def _construct_float(loader, node):
    return _parse_float(loader.construct_scalar(node))


# Explicitly tagged 1.1 types are mapped onto the JSON data model so the jq
# engine never sees datetimes, bytes, sets, or tuples.
def _construct_verbatim(loader, node):
    return loader.construct_scalar(node)


def _construct_set(loader, node):
    return dict.fromkeys(loader.construct_mapping(node))


def _construct_omap(loader, node):
    out = {}
    for sub in node.value:
        out.update(loader.construct_mapping(sub))
    return out


def _construct_pairs(loader, node):
    out = []
    for sub in node.value:
        for k, v in loader.construct_mapping(sub).items():
            out.append([k, v])
    return out


for _tag, _fn in [
        ("tag:yaml.org,2002:null", _construct_null),
        ("tag:yaml.org,2002:bool", _construct_bool),
        ("tag:yaml.org,2002:int", _construct_int),
        ("tag:yaml.org,2002:float", _construct_float),
        ("tag:yaml.org,2002:timestamp", _construct_verbatim),
        ("tag:yaml.org,2002:binary", _construct_verbatim),
        ("tag:yaml.org,2002:value", _construct_verbatim),
        ("tag:yaml.org,2002:set", _construct_set),
        ("tag:yaml.org,2002:omap", _construct_omap),
        ("tag:yaml.org,2002:pairs", _construct_pairs),
]:
    for _cls in _LOADERS:
        _cls.add_constructor(_tag, _fn)


# --- loading -----------------------------------------------------------------

def load_all(text):
    """Parse a YAML stream; returns a list with one value per document."""
    try:
        return list(yaml.load_all(text, Loader=Loader))
    except yaml.YAMLError as e:
        raise YamlError("invalid YAML: %s" % e) from None


def load(text):
    """Parse a single-document YAML string (None for an empty stream)."""
    docs = load_all(text)
    if len(docs) > 1:
        raise YamlError("expected a single YAML document, got %d" % len(docs))
    return docs[0] if docs else None


# --- dumping -----------------------------------------------------------------

# Strings that a YAML 1.2 core *or* legacy 1.1 loader would read back as a
# non-string: 1.2 scalars, 1.1 bools (yes/no/on/off/y/n), 1.1 octal/binary
# and underscored numbers, sexagesimals, timestamps, "=" and "<<".
_AMBIGUOUS = re.compile(
    r"~|null|Null|NULL"
    r"|true|True|TRUE|false|False|FALSE"
    r"|y|Y|n|N|yes|Yes|YES|no|No|NO|on|On|ON|off|Off|OFF"
    r"|[-+]?[0-9][0-9_]*|[-+]?0[obx][0-9a-fA-F_]+"
    r"|[-+]?(?:\.[0-9][0-9_]*|[0-9][0-9_]*(?:\.[0-9_]*)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+(?:\.[0-9_]*)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)"
    r"|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}([Tt ].*)?"
    r"|=|<<")


def _represent_str(dumper, data):
    style = "'" if _AMBIGUOUS.fullmatch(data) else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


for _cls in _DUMPERS:
    _cls.add_representer(str, _represent_str)

# The C classes are preferred when available; both see identical resolvers,
# constructors and representers, so behavior is the same either way.
Loader = CoreCLoader
Dumper = CoreCDumper

_NO_WRAP = 0x7FFFFFFF


def dump(value, indent=2, flow=False):
    """Serialize one value as a YAML document (always newline-terminated)."""
    try:
        text = yaml.dump(
            value, Dumper=Dumper, sort_keys=False,
            default_flow_style=flow, allow_unicode=True,
            indent=indent, width=_NO_WRAP)
    except yaml.YAMLError as e:
        raise YamlError("cannot serialize to YAML: %s" % e) from None
    if text.endswith("\n...\n"):  # PyYAML's end marker after scalar documents
        text = text[:-4]
    return text


def dump_all(values, indent=2, flow=False):
    """Serialize values as a YAML stream with `---` separators."""
    return "---\n".join(dump(v, indent=indent, flow=flow) for v in values)
