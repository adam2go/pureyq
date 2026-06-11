"""XML codec: stdlib ElementTree with the xmltodict mapping convention.

Attributes become "@name" keys, text content "#text" (or the value itself
for leaf elements), and repeated sibling elements collapse into a list.
All scalar content stays a string on load; use jq's `tonumber` to cast.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

__all__ = ["load_all", "dump_all"]


def _elem_to_value(elem):
    children = list(elem)
    d = {"@" + k: v for k, v in elem.attrib.items()}
    text = (elem.text or "").strip()
    if not children and not d:
        return text if text else None
    for child in children:
        v = _elem_to_value(child)
        if child.tag in d:
            prev = d[child.tag]
            if isinstance(prev, list):
                prev.append(v)
            else:
                d[child.tag] = [prev, v]
        else:
            d[child.tag] = v
    if text:
        d["#text"] = text
    return d


def load_all(text):
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError("invalid XML: %s" % e) from None
    return [{root.tag: _elem_to_value(root)}]


def _text(v):
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    return str(v)


def _fill(elem, value):
    if isinstance(value, dict):
        for k, v in value.items():
            if k.startswith("@"):
                elem.set(k[1:], _text(v))
            elif k == "#text":
                elem.text = _text(v)
            elif isinstance(v, list):
                for item in v:
                    _fill(ET.SubElement(elem, k), item)
            else:
                _fill(ET.SubElement(elem, k), v)
    elif value is not None:
        elem.text = _text(value)


def dump_all(values, indent=2, compact=False):
    parts = []
    for value in values:
        if not isinstance(value, dict) or len(value) != 1:
            raise ValueError("XML output requires an object with exactly "
                             "one top-level key (the root element)")
        (tag, content), = value.items()
        root = ET.Element(tag)
        _fill(root, content)
        if not compact:
            ET.indent(root, space=" " * indent)
        parts.append(ET.tostring(root, encoding="unicode") + "\n")
    return "".join(parts)
