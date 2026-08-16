#!/usr/bin/env python3
"""Turn experiments/ablation/results/*.json into the master results table.

Prints markdown to stdout. Deltas are against the `baseline` variant; the
noise floor is the spread of the seed replicates, and any delta smaller than
it is marked as below noise rather than reported as an effect.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

GROUP_ORDER = ["baseline", "noise", "ensemble", "mixing", "preprocess", "integrity"]


def load():
    out = {}
    for path in sorted(glob.glob(os.path.join(HERE, "results", "*.json"))):
        with open(path) as f:
            r = json.load(f)
        out[r["id"]] = r
    return out


def meta():
    """id -> (group, description) from variants.tsv."""
    info = {}
    with open(os.path.join(HERE, "variants.tsv")) as f:
        next(f)
        for line in f:
            if not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            info[parts[0]] = (parts[3], parts[4])
    return info


def bpc(r, corpus):
    c = r.get("corpora", {}).get(corpus)
    return c["bits_per_char"] if c else None


def fmt(v, places=4):
    return "-" if v is None else ("%%.%df" % places) % v


def signed(v):
    if v is None:
        return "-"
    return ("+%.4f" if v >= 0 else "%.4f") % v


def main():
    results = load()
    info = meta()

    if "baseline" not in results:
        print("no baseline result yet; nothing to compare against",
              file=sys.stderr)
        return 1
    base = results["baseline"]

    # Noise floor: how far the seed replicates move the number when nothing
    # about the model has changed.
    seeds = [bpc(results[i], "input2") for i in ("baseline", "seed1", "seed7919")
             if i in results and bpc(results[i], "input2") is not None]
    noise = (max(seeds) - min(seeds)) if len(seeds) > 1 else None

    print("| Variant | Group | Models | input 0.05 MB | Δ | input2 0.93 MB | Δ | Verdict |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")

    rows = sorted(results.values(), key=lambda r: (
        GROUP_ORDER.index(info.get(r["id"], ("integrity",))[0])
        if info.get(r["id"], ("integrity",))[0] in GROUP_ORDER else 99,
        -(bpc(r, "input2") or 0)))

    for r in rows:
        group, _ = info.get(r["id"], ("?", ""))
        b1, b2 = bpc(r, "input"), bpc(r, "input2")
        d1 = None if b1 is None else b1 - bpc(base, "input")
        d2 = None if b2 is None else b2 - bpc(base, "input2")

        if r.get("failed"):
            verdict = "**FAILED** " + r.get("error", "")[:60]
        elif r["id"] == "baseline":
            verdict = "reference"
        elif d2 is None:
            verdict = "-"
        elif noise is not None and abs(d2) <= noise:
            verdict = "below noise"
        elif d2 < 0:
            verdict = "**improves**"
        else:
            verdict = "costs bits"

        print("| `%s` | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], group, r.get("num_models") or "-",
            fmt(b1), signed(d1), fmt(b2), signed(d2), verdict))

    print()
    if noise is not None:
        print("Noise floor (seed replicate spread on input2): **%.4f bits/char**."
              % noise)
    fails = [r["id"] for r in results.values() if r.get("failed")]
    if fails:
        print("\nFailed variants: " + ", ".join(sorted(fails)))
    rt = [r["id"] for r in results.values() if r.get("roundtrip_ok") is False]
    if rt:
        print("Round-trip failures: " + ", ".join(sorted(rt)))

    hosts = sorted({r.get("host_cpu", "?") for r in results.values()})
    print("\nHosts: " + "; ".join(hosts))

    if "fxcm" in results and "fxcm_check" in results:
        a = bpc(results["fxcm"], "input2")
        b = bpc(results["fxcm_check"], "input2")
        print("\nCross-host integrity (fxcm vs fxcm_check on input2): %s vs %s -- %s"
              % (fmt(a), fmt(b),
                 "match" if a == b else "**MISMATCH, do not pool shards**"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
