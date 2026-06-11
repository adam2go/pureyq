"""Benchmark pureyq against mikefarah/yq (Go) and kislyuk/yq (jq wrapper).

Usage:
    python tools/bench.py [N] [--runs 7] [--verify]

N is the large-corpus row count (default 100000). --verify first checks that
every contestant produces semantically identical output for every workload
(values compared after parsing, since formatting legitimately differs), and
refuses to print timings for workloads that disagree.

Reference binaries are found via $YQ_BIN (mikefarah, default: `yq` on PATH)
and $KYQ_BIN (kislyuk's wrapper; skipped when absent). Timings are medians
of wall-clock runs, startup included for the CLI workloads - that is what a
shell or an agent actually pays.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pureyq  # noqa: E402
from pureyq.formats import yaml12  # noqa: E402

MANIFEST = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: prod
  labels:
    app: web
    tier: frontend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: app
          image: registry.example.com/web:v1.4.2
          ports:
            - containerPort: 8080
          env:
            - name: LOG_LEVEL
              value: info
            - name: COUNTRY
              value: 'NO'
          resources:
            limits:
              cpu: 500m
              memory: 512Mi
"""

FIRST = ["Ada", "Bob", "Chen", "Dee", "Eve", "Finn", "Gus", "Hana", "Ivy", "Jo"]
CITY = ["Oslo", "Bergen", "Lyon", "Kyoto", "Quito", "Perth", "Pune", "Lima"]


def make_rows(n):
    rows = []
    for i in range(n):
        rows.append({
            "id": i,
            "name": "%s-%04d" % (FIRST[i % 10], i),
            "age": (i * 7919) % 90 + 10,
            "active": i % 3 == 0,
            "score": round((i % 1000) / 7.0, 3),
            "team": "team-%02d" % (i % 16),
            "tags": ["t%d" % (i % 5), "t%d" % (i % 11)],
            "address": {"city": CITY[i % 8], "zip": "%05d" % (i % 99999)},
        })
    return rows


def median_time(cmd, runs):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        subprocess.run(cmd, stdout=subprocess.DEVNULL, check=True)
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def output_of(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def parse_any(text):
    return yaml12.load_all(text)  # YAML 1.2 is a superset of JSON


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=100000)
    ap.add_argument("--runs", type=int, default=7)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    pureyq_bin = os.path.join(os.path.dirname(sys.executable), "pureyq")
    if not os.path.exists(pureyq_bin):
        sys.exit("pureyq console script not found next to %s" % sys.executable)
    yq = os.environ.get("YQ_BIN") or shutil.which("yq")
    kyq = os.environ.get("KYQ_BIN")

    tmp = tempfile.mkdtemp(prefix="pureyq-bench-")
    small = os.path.join(tmp, "deploy.yaml")
    with open(small, "w") as f:
        f.write(MANIFEST)
    big = os.path.join(tmp, "big.yaml")
    rows = make_rows(args.n)
    t0 = time.perf_counter()
    with open(big, "w") as f:
        f.write(yaml12.dump(rows))
    gen = time.perf_counter() - t0
    size = os.path.getsize(big) / 1e6
    print("corpus: %s rows -> %.1f MB YAML (generated in %.2fs); runs=%d"
          % (args.n, size, gen, args.runs))
    print("contestants: pureyq=%s  yq=%s  kislyuk-yq=%s\n"
          % (pureyq_bin, yq or "MISSING", kyq or "skipped"))

    edit = ".spec.replicas = 3"
    filt = "[.[] | select(.age > 50)] | length"
    workloads = [
        ("small manifest edit", [
            ("pureyq", [pureyq_bin, edit, small]),
            ("yq (Go)", [yq, edit, small] if yq else None),
            ("kislyuk yq", [kyq, "-y", edit, small] if kyq else None),
        ]),
        ("large filter+count", [
            ("pureyq", [pureyq_bin, filt, big]),
            ("yq (Go)", [yq, filt, big] if yq else None),
            ("kislyuk yq", [kyq, filt, big] if kyq else None),
        ]),
        ("large yaml -> json", [
            ("pureyq", [pureyq_bin, "-o", "json", "-c", ".", big]),
            ("yq (Go)", [yq, "-o=json", "-I0", ".", big] if yq else None),
            ("kislyuk yq", [kyq, "-c", ".", big] if kyq else None),
        ]),
    ]

    for title, entries in workloads:
        entries = [(name, cmd) for name, cmd in entries if cmd]
        if args.verify:
            outs = {name: parse_any(output_of(cmd)) for name, cmd in entries}
            base = outs[entries[0][0]]
            bad = [n for n, v in outs.items() if v != base]
            if bad:
                print("%-22s VERIFY FAILED: %s disagree" % (title, bad))
                continue
            print("%-22s verified: %d contestants agree" % (title, len(entries)))
        for name, cmd in entries:
            print("    %-12s %8.0f ms" % (name, median_time(cmd, args.runs) * 1000))
        print()

    # Embedded: transform text in-process vs spawning the Go binary per call.
    prog = pureyq.compile(edit)
    reps = 200
    t0 = time.perf_counter()
    for _ in range(reps):
        out_lib = pureyq.apply(prog, MANIFEST)
    lib_ms = (time.perf_counter() - t0) / reps * 1000
    print("embedded transform (per call, %d reps):" % reps)
    print("    %-22s %8.3f ms" % ("pureyq.apply()", lib_ms))
    if yq:
        if args.verify:
            ref = output_of([yq, edit, small])
            assert yaml12.load_all(out_lib) == yaml12.load_all(ref), \
                "embedded output disagrees with yq"
            print("    (embedded output verified against yq)")
        t = median_time([yq, edit, small], args.runs)
        print("    %-22s %8.3f ms" % ("subprocess yq (Go)", t * 1000))


if __name__ == "__main__":
    main()
