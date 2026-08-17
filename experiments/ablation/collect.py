#!/usr/bin/env python3
"""Turn experiments/ablation/results/<mode>/*.json into the results tables.

The dictionary is an ablation axis, not a setting chosen once: the same
mechanism can earn a different amount depending on whether the WRT transform
already removed the redundancy it exploits. Each preprocessing mode is
therefore its own arm, with its own baseline and its own noise floor, and rows
from the non-dictionary arm are suffixed `-no-dict` so a single table can carry
both without the deltas being silently cross-compared.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

GROUP_ORDER = ["baseline", "noise", "ensemble", "mixing", "preprocess", "integrity"]
SUFFIX = {"dict": "", "nodict": "-no-dict", "noprep": "-no-prep"}


def load(mode=None):
    out = {}
    for path in sorted(glob.glob(os.path.join(HERE, "results", mode or "*", "*.json"))):
        try:
            with open(path) as f:
                r = json.load(f)
        except ValueError:
            continue
        if mode and r.get("mode") != mode:
            continue
        out[r["id"]] = r
    return out


def modes_present():
    found = set()
    for path in glob.glob(os.path.join(HERE, "results", "*", "*.json")):
        try:
            found.add(json.load(open(path)).get("mode", "?"))
        except ValueError:
            pass
    return [m for m in ("dict", "nodict", "noprep") if m in found]


def meta():
    info = {}
    with open(os.path.join(HERE, "variants.tsv")) as f:
        next(f)
        for line in f:
            if not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            info[p[0]] = (p[3], p[4])
    return info


def bpc(r, corpus):
    c = r.get("corpora", {}).get(corpus)
    return c["bits_per_char"] if c else None


def fmt(v, places=4):
    return "-" if v is None else ("%%.%df" % places) % v


def signed(v):
    return "-" if v is None else (("+%.4f" if v >= 0 else "%.4f") % v)


def noise_floor(results, corpus):
    seeds = [bpc(results[i], corpus) for i in ("baseline", "seed1", "seed7919")
             if i in results and bpc(results[i], corpus) is not None]
    return (max(seeds) - min(seeds)) if len(seeds) > 1 else None


def table(info):
    """One table across all arms; non-dictionary rows carry a -no-dict suffix."""
    print("| Variant | Group | Models | input 0.05 MB | Δ | input2 0.93 MB | Δ "
          "| UPX exe | Δ exe | Verdict |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")

    floors = {}
    for mode in modes_present():
        results = load(mode)
        base = results.get("baseline")
        # Every delta is against the baseline of its own arm. Comparing across
        # arms would fold the dictionary's own effect into every mechanism.
        b1 = bpc(base, "input") if base else None
        b2 = bpc(base, "input2") if base else None
        floor_corpus = "input2" if b2 is not None else "input"
        floor = noise_floor(results, floor_corpus)
        floors[mode] = (floor, floor_corpus)
        sfx = SUFFIX[mode]

        rows = sorted(results.values(), key=lambda r: (
            GROUP_ORDER.index(info.get(r["id"], ("integrity",))[0])
            if info.get(r["id"], ("integrity",))[0] in GROUP_ORDER else 99,
            -(bpc(r, "input2") or bpc(r, "input") or 0)))

        for r in rows:
            group = info.get(r["id"], ("?", ""))[0]
            v1, v2 = bpc(r, "input"), bpc(r, "input2")
            d1 = None if (v1 is None or b1 is None) else v1 - b1
            d2 = None if (v2 is None or b2 is None) else v2 - b2
            dprim = d2 if d2 is not None else d1

            if r.get("failed"):
                verdict = "**FAILED**"
            elif r["id"] == "baseline":
                verdict = "reference"
            elif dprim is None:
                verdict = "-"
            elif floor is not None and round(abs(dprim), 4) <= round(floor, 4):
                verdict = "below noise"
            elif dprim < 0:
                verdict = "**improves**"
            else:
                verdict = "costs bits"

            upx = r.get("exe_upx_bytes")
            bupx = base.get("exe_upx_bytes") if base else None
            dupx = None if (upx is None or bupx is None) else upx - bupx

            print("| `%s%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["id"], sfx, group, r.get("num_models") or "-",
                fmt(v1), signed(d1), fmt(v2), signed(d2),
                upx or "-", "-" if dupx is None else "%+d" % dupx, verdict))

    print()
    for mode, (floor, corpus) in floors.items():
        if floor is not None:
            print("Noise floor, `%s` arm (seed spread on `%s`): **%.4f bits/char**.  "
                  % (mode, corpus, floor))


def break_even(corpus="input2"):
    """Corpus size at which a mechanism's savings overtake its own code cost.

    S = S1 (executable) + S2 (archive), so a mechanism costing E bytes of
    binary and saving d bits/char breaks even at N = E / (d/8) bytes.
    """
    results = load("dict") or load("nodict")
    base = results.get("baseline")
    if not base or not base.get("exe_upx_bytes"):
        return ""
    c = corpus if bpc(base, corpus) is not None else "input"
    bb = bpc(base, c)
    if bb is None:
        return ""

    rows = []
    for r in results.values():
        if r["id"] == "baseline" or r.get("failed"):
            continue
        upx, v = r.get("exe_upx_bytes"), bpc(r, c)
        if not upx or v is None:
            continue
        cost, d = base["exe_upx_bytes"] - upx, v - bb
        if cost > 0 and d > 0:
            rows.append((cost / (d / 8.0), r["id"], cost, d))
    if not rows:
        return ""

    rows.sort()
    out = ["", "### Break-even corpus size", "",
           "_Savings measured on `%s`, dictionary arm._" % c, "",
           "| Mechanism | Exe cost (B) | Saves (bits/char) | Breaks even at |",
           "| --- | ---: | ---: | ---: |"]
    for n, vid, cost, d in rows:
        size = "%.1f KB" % (n / 1e3) if n < 1e6 else "%.1f MB" % (n / 1e6)
        out.append("| `%s` | %d | %.4f | %s |" % (vid, cost, d, size))
    out.append("")
    out.append("enwik9 is 1 000 MB, so anything breaking even well below that "
               "earns its place.")
    return "\n".join(out)


def interaction(corpus="input2"):
    """Does a mechanism earn more or less once the dictionary is applied?

    WRT rewrites words as 1-3 byte codes and permutes the byte alphabet, so a
    mechanism exploiting word or markup redundancy may find it already gone --
    or concentrated into a form it reads better. The sign differs by mechanism,
    which is the reason both arms are run.
    """
    a, b = load("dict"), load("nodict")
    if "baseline" not in a or "baseline" not in b:
        return ""
    ba, bb = bpc(a["baseline"], corpus), bpc(b["baseline"], corpus)
    if ba is None or bb is None:
        return ""

    rows = []
    for vid in sorted(set(a) & set(b)):
        if vid == "baseline" or vid.startswith("seed"):
            continue
        va, vb = bpc(a[vid], corpus), bpc(b[vid], corpus)
        if va is None or vb is None:
            continue
        rows.append((abs((va - ba) - (vb - bb)), vid, va - ba, vb - bb))
    if not rows:
        return ""

    rows.sort(reverse=True)
    out = ["", "### Dictionary interaction (`%s`)" % corpus, "",
           "What each mechanism costs when removed, measured separately in "
           "both arms. A large shift means the mechanism and the dictionary "
           "compete for the same redundancy.", "",
           "| Mechanism | Δ with dict | Δ without dict | Shift |",
           "| --- | ---: | ---: | ---: |"]
    for _, vid, da, db in rows:
        out.append("| `%s` | %s | %s | %s |"
                   % (vid, signed(da), signed(db), signed(da - db)))
    out.append("")
    out.append("A delta that shrinks under the dictionary means the mechanism "
               "was partly doing the dictionary's job; one that grows means it "
               "reads the coded stream better than raw text.")
    out.append("")
    out.append("_Caveat: the two arms were not built identically. The "
               "no-dictionary arm is non-PGO `-march=x86-64-v3`, the "
               "dictionary arm is PGO `-march=native`. That difference "
               "measures 0.0001-0.0002 bits/char, below both arms' noise "
               "floors, so it does not affect the ranking -- but do not read "
               "shifts of that size as real._")
    return "\n".join(out)


def main():
    if not modes_present():
        print("no results yet", file=sys.stderr)
        return 1
    table(meta())
    for section in (break_even(), interaction()):
        if section:
            print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
