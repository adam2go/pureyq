"""pureyq: yq as a pure Python library - jq syntax over YAML, TOML, XML, CSV.

The jq engine is purejq (same author); pureyq adds the multi-format layer.
No jq binary, no C extension: if Python runs, pureyq runs.

    import pureyq

    data = pureyq.load(yaml_text)                    # YAML 1.2 -> Python
    pureyq.first(".spec.replicas", data)             # jq over Python objects
    pureyq.apply(".spec.replicas = 3", yaml_text)    # text -> text, one call
"""
from __future__ import annotations

from purejq import (JqError, JqParseError, all_outputs,  # noqa: F401
                    compile, first)

from . import formats
from .formats.yaml12 import YamlError, dump, dump_all, load, load_all  # noqa: F401

__version__ = "0.1.0"
__all__ = ["compile", "first", "all_outputs", "apply",
           "load", "load_all", "dump", "dump_all",
           "JqError", "JqParseError", "YamlError"]


def apply(program, text, input_format="yaml", output_format=None,
          indent=2, compact=False):
    """Run a jq program over config text; returns the transformed text.

    ``program`` may be a jq source string or a compiled ``pureyq.compile()``
    program. Multi-document YAML streams run the program once per document.
    """
    prog = compile(program) if isinstance(program, str) else program
    docs = formats.load_all(input_format, text)
    it = iter(docs)
    outputs = []
    for doc in it:
        outputs.extend(prog.run(doc, inputs=it))
    return formats.dump_all(output_format or input_format, outputs,
                            indent=indent, compact=compact)
