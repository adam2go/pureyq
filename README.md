# pureyq

[![CI](https://github.com/adam2go/pureyq/actions/workflows/ci.yml/badge.svg)](https://github.com/adam2go/pureyq/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pureyq)](https://pypi.org/project/pureyq/)
[![Python](https://img.shields.io/badge/python-3.9%E2%80%933.14%20%7C%20PyPy-blue)](.github/workflows/ci.yml)
[![toml-test](https://img.shields.io/badge/toml--test%20suite-100%25-brightgreen)](tests/test_toml_conformance.py)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**[yq](https://github.com/mikefarah/yq), as a pure Python library.** Run jq
programs over YAML, TOML, XML, CSV and JSON — no yq binary, no jq binary,
no C extension required: if Python runs, pureyq runs. Pyodide/WASM,
sandboxes, Lambda, anywhere `pip install` is all you get.

```sh
pip install pureyq
```

```sh
pureyq -i '.spec.replicas = 3' deploy.yaml          # edit YAML in place
pureyq -o json '.services | keys' compose.yaml      # YAML in, JSON out
pureyq '.dependencies' pyproject.toml               # TOML works the same way
```

```python
import pureyq

pureyq.apply(".spec.replicas = 3", manifest_text)   # text -> text, one call
data = pureyq.load(manifest_text)                   # YAML 1.2 -> Python
pureyq.first(".spec.template.spec.containers[].image", data)
```

The expression language is **jq** — the real one, not a dialect: the engine
is [purejq](https://github.com/adam2go/purejq), which passes 96.2% of jq's
own test suite. Everything you know from jq works on your YAML:
`select`, `map`, `group_by`, paths, assignment operators, `reduce`,
`try/catch`, string interpolation, regexes.

## Why pureyq

- **No binaries, anywhere.** [kislyuk/yq](https://github.com/kislyuk/yq)
  needs a jq binary on the system at runtime; mikefarah/yq *is* a Go binary.
  In sandboxed or `pip`-only environments (Pyodide, Lambda layers, locked-down
  CI images, agent sandboxes) neither is an option. pureyq is plain Python
  wheels all the way down.
- **Embedding in Python.** Transforming a manifest in-process with
  `pureyq.apply()` takes a fraction of a millisecond; spawning a yq binary
  per call costs milliseconds. For agent/automation loops that edit many
  small configs, in-process wins by an order of magnitude.
- **YAML 1.2 correctness by default.** PyYAML-based tools (including
  kislyuk/yq) speak YAML 1.1, with famous consequences:

  | input | YAML 1.1 loaders read | pureyq (1.2 Core Schema) |
  |---|---|---|
  | `country: NO` | `false` (!) | `"NO"` |
  | `version: 010` | `8` (octal) | `10` |
  | `time: 1:30` | `90` (sexagesimal) | `"1:30"` |
  | `date: 2026-06-11` | a datetime object | `"2026-06-11"` |

  On output, strings that *either* YAML generation would misread are quoted
  automatically, so emitted files are safe for downstream 1.1 parsers too.
  Merge keys (`<<:`) still work — real-world configs depend on them.

## Formats

| | input | output | notes |
|---|---|---|---|
| YAML | ✓ | ✓ | multi-document streams, merge keys, 1.2 Core Schema |
| JSON | ✓ | ✓ | jq-identical output via purejq's encoder |
| TOML | ✓ | ✓ | 100% of the official [toml-test](https://github.com/toml-lang/toml-test) suite (704 cases, vendored, run in CI); datetimes load as ISO strings |
| XML | ✓ | ✓ | xmltodict convention: `@attr`, `#text`, repeated tags become lists |
| CSV/TSV | ✓ | ✓ | header row + typed cells (leading-zero ZIP codes stay strings) |

Input format is detected from the file extension (`-p` to force); output
defaults to the input format (`-o` to convert). `pureyq -o json . config.toml`
and `pureyq -o yaml . data.json` are complete format converters.

## CLI

```
pureyq [options] '<jq filter>' [files...]

-p FMT   input format: auto|yaml|json|toml|xml|csv|tsv (default: by extension)
-o FMT   output format (default: same as input)
-i       edit files in place (atomic; preserves permissions)
-n -r -j -c -s -e -f --arg --argjson    the flags you know from jq
--indent N    output indentation
```

Multi-document YAML streams behave like jq input streams: each document is
one program run, `--slurp` collects them into an array, and `input`/`inputs`
consume the rest.

## Benchmarks

Measured with [tools/bench.py](tools/bench.py): M-series MacBook, CPython
3.12, mikefarah yq v4.53.3 (native arm64 binary), kislyuk/yq 3.4.3 over jq
1.8 — **five independent rounds, each the median of 7 runs, and every
workload's outputs verified equal across all three tools before timing**.
The numbers below are cross-round medians; round-to-round spread was under
4%. Reproduce: `python tools/bench.py --verify`.

**Embedded in Python** — editing a k8s manifest, per call:

| | per call |
|---|---:|
| `pureyq.apply()` (in-process) | 0.16 ms |
| spawning the Go yq binary | 5.4 ms |

In-process beats shelling out ~34x. For agent/automation loops that touch
many configs, this is the number that matters.

**Command line, small file** — 40-line k8s manifest, startup included:

| pureyq | yq (Go) | kislyuk/yq (jq wrapper) |
|---:|---:|---:|
| 35 ms | 5 ms | 44 ms |

**Command line, big file** — 15 MB YAML, 100k objects, end to end:

| workload | pureyq | yq (Go) | kislyuk/yq |
|---|---:|---:|---:|
| filter + count | 7.1 s | 1.0 s | 6.4 s |
| convert to JSON | 6.4 s | 2.7 s | 6.8 s |

Where the Go binary wins: big-file throughput, by 2–7x. If you can install
binaries and that is your workload, use mikefarah/yq. pureyq's lane is
everywhere binaries can't go, in-process embedding, and doing what the
jq-wrapper approach does without needing jq. (One caveat on the Go side:
its compact-JSON mode `-I0` is quadratic on large arrays — converting the
same 20k-row file takes it 104 s vs pureyq's 1.2 s — so agents asking for
compact JSON from big YAML hit a wall pureyq doesn't have.)

## Correctness, measured

- **TOML**: the official toml-test suite is vendored in this repo
  ([tests/conformance/toml-test](tests/conformance/toml-test)) and runs in CI
  on every commit: **704/704 of the TOML 1.0 cases pass** (209 valid
  documents match the typed expectations, 495 invalid documents are
  rejected).
- **jq semantics**: inherited from [purejq](https://github.com/adam2go/purejq),
  which vendors jq's own test suite (751/781 passing, every difference
  documented).
- **YAML 1.2 schema**: a directed test set covers the 1.1/1.2 divergences
  (booleans, octals, sexagesimals, timestamps, `.inf/.nan`, quoting on
  output), and the libyaml fast path is asserted to agree with the pure
  Python fallback on every case.

## Limitations (honest ones)

- **Comments and exact formatting are not preserved** through an edit, same
  as kislyuk/yq. (mikefarah/yq can preserve them because its engine operates
  on the YAML node tree; a jq engine works on values.) Anchors/aliases are
  resolved on load and not re-emitted.
- TOML output requires a single object result (that's what a TOML document
  *is*); CSV output requires flat rows.
- When PyYAML carries its libyaml C extension (standard wheels do), pureyq
  uses it for parsing speed — with a pure Python fallback that behaves
  identically, asserted by tests. "Pure" means *required by*, not *faster
  with*.

## License

[MIT](LICENSE)
