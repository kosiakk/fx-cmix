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


def break_even(results, base):
    """At what corpus size does each mechanism pay back its own binary cost?

    The Hutter Prize scores S = S1 (executable) + S2 (archive). Keeping a
    mechanism costs E = exe_upx(full) - exe_upx(ablated) bytes of executable,
    and saves d = delta bits/char on every byte of input. So it breaks even at
    N = E / (d/8) bytes of corpus. Below that size the mechanism is dead weight;
    above it, it pays.

    Measured on ~1 MB, so d for long-range mechanisms is understated and these
    figures are pessimistic for them. Treat as an order of magnitude.
    """
    base_upx = base.get("exe_upx_bytes")
    corpus = "input2" if bpc(base, "input2") is not None else "input"
    base_bpc = bpc(base, corpus)
    if not base_upx or base_bpc is None:
        return "Break-even sizes need the baseline's exe size and a corpus result."

    rows = []
    for r in results.values():
        if r["id"] == "baseline" or r.get("failed"):
            continue
        upx, b2 = r.get("exe_upx_bytes"), bpc(r, corpus)
        if not upx or b2 is None:
            continue
        exe_cost = base_upx - upx          # bytes of binary the mechanism costs
        d = b2 - base_bpc                  # bits/char the mechanism saves
        if exe_cost <= 0 or d <= 0:
            continue
        rows.append((exe_cost / (d / 8.0), r["id"], exe_cost, d))

    if not rows:
        return "No mechanism has both a positive binary cost and a positive saving yet."

    rows.sort()
    out = ["### Break-even corpus size",
           "",
           "_Savings measured on `%s`._" % corpus,
           "",
           "How much input a mechanism must see before the bytes it saves "
           "exceed the bytes its code costs in the packed executable.",
           "",
           "| Mechanism | Exe cost (B) | Saves (bits/char) | Breaks even at |",
           "| --- | ---: | ---: | ---: |"]
    for n, vid, cost, d in rows:
        size = ("%.1f KB" % (n / 1e3)) if n < 1e6 else ("%.1f MB" % (n / 1e6))
        out.append("| `%s` | %d | %.4f | %s |" % (vid, cost, d, size))
    out.append("")
    out.append("enwik9 is 1 000 MB, so anything breaking even well below that "
               "earns its place; anything near or above it is a candidate for "
               "removal on a size-scored benchmark.")
    return "\n".join(out)


def main():
    results = load()
    info = meta()

    if "baseline" not in results:
        print("no baseline result yet; nothing to compare against",
              file=sys.stderr)
        return 1
    base = results["baseline"]

    # Noise floor: how far the seed replicates move the number when nothing
    # about the model has changed. Falls back to the small corpus while the
    # full pass is still running.
    noise_corpus = "input2" if bpc(base, "input2") is not None else "input"
    seeds = [bpc(results[i], noise_corpus)
             for i in ("baseline", "seed1", "seed7919")
             if i in results and bpc(results[i], noise_corpus) is not None]
    noise = (max(seeds) - min(seeds)) if len(seeds) > 1 else None

    print("| Variant | Group | Models | input 0.05 MB | Δ | input2 0.93 MB | Δ | UPX exe | Δ exe | Verdict |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")

    rows = sorted(results.values(), key=lambda r: (
        GROUP_ORDER.index(info.get(r["id"], ("integrity",))[0])
        if info.get(r["id"], ("integrity",))[0] in GROUP_ORDER else 99,
        -(bpc(r, "input2") or 0)))

    # The baseline may not cover both corpora yet (a --quick pass covers only
    # the small one), so a delta is only defined where both sides exist.
    base1, base2 = bpc(base, "input"), bpc(base, "input2")

    for r in rows:
        group, _ = info.get(r["id"], ("?", ""))
        b1, b2 = bpc(r, "input"), bpc(r, "input2")
        d1 = None if (b1 is None or base1 is None) else b1 - base1
        d2 = None if (b2 is None or base2 is None) else b2 - base2

        # Judge on the largest corpus this variant actually has, so the table
        # stays meaningful while the full pass is still filling in.
        dprim = d2 if d2 is not None else d1

        if r.get("failed"):
            verdict = "**FAILED** " + r.get("error", "")[:60]
        elif r["id"] == "baseline":
            verdict = "reference"
        elif dprim is None:
            verdict = "-"
        elif noise is not None and round(abs(dprim), 4) <= round(noise, 4):
            # Rounded, or a delta sitting exactly on the floor is classified by
            # floating-point dust rather than by the measurement.
            verdict = "below noise"
        elif dprim < 0:
            verdict = "**improves**"
        else:
            verdict = "costs bits"

        upx = r.get("exe_upx_bytes")
        dupx = None if (upx is None or base.get("exe_upx_bytes") is None) \
            else upx - base["exe_upx_bytes"]

        print("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], group, r.get("num_models") or "-",
            fmt(b1), signed(d1), fmt(b2), signed(d2),
            upx if upx else "-",
            "-" if dupx is None else ("%+d" % dupx), verdict))

    print()
    print(break_even(results, base))
    print()
    if noise is not None:
        print("Noise floor (seed replicate spread on `%s`): **%.4f bits/char**."
              % (noise_corpus, noise))
    fails = [r["id"] for r in results.values() if r.get("failed")]
    if fails:
        print("\nFailed variants: " + ", ".join(sorted(fails)))
    rt = [r["id"] for r in results.values() if r.get("roundtrip_ok") is False]
    if rt:
        print("Round-trip failures: " + ", ".join(sorted(rt)))

    hosts = sorted({r.get("host_cpu", "?") for r in results.values()})
    print("\nHosts: " + "; ".join(hosts))

    if "fxcm" in results and "fxcm_check" in results:
        for c in ("input2", "input"):
            a, b = bpc(results["fxcm"], c), bpc(results["fxcm_check"], c)
            if a is None or b is None:
                continue
            ha = results["fxcm"].get("host_cpu")
            hb = results["fxcm_check"].get("host_cpu")
            print("\nIntegrity check on `%s`: fxcm %s vs fxcm_check %s -- %s"
                  % (c, fmt(a), fmt(b),
                     "identical" if a == b
                     else "**MISMATCH, do not pool results**"))
            print("Built on %s and %s." % (ha, hb)
                  + ("" if ha != hb else
                     " Same host, so this checks determinism rather than"
                     " cross-host reproducibility."))
            break
        else:
            print("\nIntegrity check: pending, no corpus covered by both yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
