"""Command-line interface: jq programs over YAML, TOML, XML, CSV and JSON.

Mirrors purejq's flag set and adds the format layer: ``-p`` input format
(auto-detected from file extensions by default), ``-o`` output format
(defaults to the input format), and ``-i`` for in-place editing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from purejq import Program
from purejq.errors import Halt, JqError, JqParseError

from . import formats

_FMT_CHOICES = ("auto",) + formats.FORMAT_NAMES


def _build_parser():
    ap = argparse.ArgumentParser(
        prog="pureyq",
        description="pureyq - run jq programs over YAML, TOML, XML, CSV "
                    "and JSON, in pure Python")
    ap.add_argument("program", nargs="?", default=None, help="jq filter to run")
    ap.add_argument("files", nargs="*", help="input files (default: stdin)")
    ap.add_argument("-p", "--input-format", choices=_FMT_CHOICES, default="auto",
                    metavar="FMT", help="input format: %s (default: by file "
                    "extension, else yaml)" % "|".join(_FMT_CHOICES))
    ap.add_argument("-o", "--output-format", choices=_FMT_CHOICES, default="auto",
                    metavar="FMT", help="output format (default: same as input)")
    ap.add_argument("-i", "--in-place", action="store_true",
                    help="edit files in place")
    ap.add_argument("--indent", type=int, default=2, metavar="N",
                    help="output indentation (default: 2)")
    ap.add_argument("-n", "--null-input", action="store_true",
                    help="use null as the single input value")
    ap.add_argument("-r", "--raw-output", action="store_true",
                    help="output strings without quotes")
    ap.add_argument("-j", "--join-output", action="store_true",
                    help="like -r but without trailing newlines")
    ap.add_argument("-c", "--compact-output", action="store_true",
                    help="compact output (JSON one-liners, YAML flow style)")
    ap.add_argument("-s", "--slurp", action="store_true",
                    help="read all input documents into a single array")
    ap.add_argument("-e", "--exit-status", action="store_true",
                    help="set exit status by the last output value")
    ap.add_argument("-f", "--from-file", metavar="FILE",
                    help="read the filter from a file")
    ap.add_argument("--arg", nargs=2, action="append", default=[],
                    metavar=("NAME", "VALUE"), help="bind $NAME to a string value")
    ap.add_argument("--argjson", nargs=2, action="append", default=[],
                    metavar=("NAME", "JSON"), help="bind $NAME to a JSON value")
    return ap


def main(argv=None):
    ap = _build_parser()
    args = ap.parse_args(argv)

    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            source = f.read()
        if args.program is not None:
            args.files.insert(0, args.program)
    elif args.program is not None:
        source = args.program
    else:
        ap.error("no filter given")

    try:
        prog = Program(source)
    except JqParseError as e:
        print("pureyq: error: %s" % e, file=sys.stderr)
        return 3

    vars = {}
    for name, value in args.arg:
        vars[name] = value
    for name, value in args.argjson:
        try:
            vars[name] = json.loads(value)
        except ValueError as e:
            print("pureyq: invalid JSON for --argjson %s: %s" % (name, e),
                  file=sys.stderr)
            return 2

    if args.in_place:
        if not args.files:
            print("pureyq: -i/--in-place requires at least one file",
                  file=sys.stderr)
            return 2
        for path in args.files:
            code = _edit_file(prog, path, args, vars)
            if code:
                return code
        return 0

    try:
        fmt_in, docs = _read_inputs(args)
    except (OSError, ValueError) as e:
        print("pureyq: %s" % e, file=sys.stderr)
        return 2
    fmt_out = args.output_format if args.output_format != "auto" else fmt_in

    last = None
    had_output = False
    code = 0
    out = sys.stdout
    emitted = 0
    try:
        for value, inputs in _runs(docs, args):
            for result in prog.run(value, inputs=inputs, vars=vars):
                last = result
                had_output = True
                out.write(_render(result, fmt_out, args, emitted))
                emitted += 1
    except JqError as e:
        print("pureyq: error: %s" % e, file=sys.stderr)
        code = 5
    except ValueError as e:  # output format cannot represent the result
        print("pureyq: error: %s" % e, file=sys.stderr)
        code = 5
    except Halt as h:
        if h.payload is not None:
            if isinstance(h.payload, str):
                sys.stderr.write(h.payload)
            else:
                sys.stderr.write(json.dumps(h.payload) + "\n")
        code = h.code
    except BrokenPipeError:
        return 0

    if args.exit_status and code == 0:
        if not had_output:
            code = 4
        elif last is None or last is False:
            code = 1
    return code


def _runs(docs, args):
    """Pair each program run with the iterator feeding `input`/`inputs`."""
    if args.null_input:
        return [(None, iter(docs))]
    if args.slurp:
        return [(docs, iter(()))]
    shared = iter(docs)
    return ((v, shared) for v in shared)


def _read_inputs(args):
    """Read stdin or the input files; returns (format, list of documents)."""
    explicit = args.input_format if args.input_format != "auto" else None
    if args.files:
        fmt_first = None
        docs = []
        for path in args.files:
            fmt = explicit or formats.detect(path)
            if fmt_first is None:
                fmt_first = fmt
            # utf-8-sig eats BOMs; newline="" leaves line endings to the
            # codecs (TOML must see bare \r to reject it).
            with open(path, encoding="utf-8-sig", newline="") as f:
                docs.extend(formats.load_all(fmt, f.read()))
        return fmt_first, docs
    fmt = explicit or "yaml"
    text = "" if args.null_input else sys.stdin.read()
    return fmt, formats.load_all(fmt, text) if text else []


def _render(result, fmt_out, args, emitted):
    """Render one program output, with stream separators where needed."""
    if (args.raw_output or args.join_output) and isinstance(result, str):
        return result if args.join_output else result + "\n"
    if fmt_out == "toml" and emitted:
        raise ValueError("TOML output requires exactly one result")
    prefix = "---\n" if fmt_out == "yaml" and emitted else ""
    text = formats.dump_all(fmt_out, [result], indent=args.indent,
                            compact=args.compact_output)
    if args.join_output and text.endswith("\n"):
        text = text[:-1]
    return prefix + text


def _edit_file(prog, path, args, vars):
    fmt_in = (args.input_format if args.input_format != "auto"
              else formats.detect(path))
    fmt_out = args.output_format if args.output_format != "auto" else fmt_in
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            text = f.read()
        docs = formats.load_all(fmt_in, text)
    except (OSError, ValueError) as e:
        print("pureyq: %s: %s" % (path, e), file=sys.stderr)
        return 2

    outputs = []
    try:
        for value, inputs in _runs(docs, args):
            for result in prog.run(value, inputs=inputs, vars=vars):
                outputs.append(result)
        rendered = formats.dump_all(fmt_out, outputs, indent=args.indent,
                                    compact=args.compact_output)
    except (JqError, ValueError) as e:
        print("pureyq: %s: %s" % (path, e), file=sys.stderr)
        return 5
    except Halt as h:
        return h.code

    mode = os.stat(path).st_mode
    dirname = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=dirname, prefix=".pureyq-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(rendered)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
