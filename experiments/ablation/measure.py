#!/usr/bin/env python3
"""Measure one ablation variant: compressed size, bits/char, time, peak RSS.

Compresses both corpus files, and additionally round-trips the small one to
prove the variant is still a working codec. A variant that fails its round trip
is a bug, not a result, and is recorded as such.
"""

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import time

# Both corpora are wiki text already in the repo. input2 is a real enwik
# prefix starting at <mediawiki>; input is a mid-stream fragment.
CORPORA = [
    ("input", "prof_input/input"),
    ("input2", "prof_input/input2"),
]

NUM_MODELS_RE = re.compile(rb"num models (\d+)")


def run(cmd, cwd):
    """Run cmd, returning (elapsed_seconds, peak_rss_kb, returncode, output)."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss is the high-water mark across all reaped children, so it only
    # tells us about this child if it exceeded every previous one. Runs are
    # ordered largest-last within a variant, and each variant is its own
    # process, so this is the peak for the variant as a whole.
    return elapsed, max(after, before), proc.returncode, proc.stdout


def exe_sizes(binary):
    """Stripped and UPX-compressed size of the variant's executable.

    The Hutter Prize scores S = S1 (executable) + S2 (archive), so a mechanism
    that costs more binary bytes than it saves archive bytes is a net loss.
    These are non-PGO -O3 builds, so absolute S1 will not match a real
    submission; the differences between variants are what matter.
    """
    plain = os.path.getsize(binary)
    packed = None
    tmp = binary + ".upx"
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
        subprocess.run(["strip", "-o", tmp, binary],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(tmp):
            return plain, None, None
        stripped = os.path.getsize(tmp)
        r = subprocess.run(["upx-ucl", "-9", "-q", tmp],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            packed = os.path.getsize(tmp)
        return plain, stripped, packed
    except OSError:
        return plain, None, None


def compress_cmd(binary, mode, repo, src, dst):
    if mode == "dict":
        return [binary, "-c", os.path.join(repo, "dictionary/english.dic"), src, dst]
    if mode == "noprep":
        return [binary, "-n", src, dst]
    return [binary, "-c", src, dst]


def decompress_cmd(binary, mode, repo, src, dst):
    # Note "-n" is compress-only -- runner.cpp routes both -c and -n to
    # RunCompression, and the decompressor reads whether preprocessing was
    # applied out of the stream header. So everything decompresses with -d.
    if mode == "dict":
        return [binary, "-d", os.path.join(repo, "dictionary/english.dic"), src, dst]
    return [binary, "-d", src, dst]


def main():
    ap = argparse.ArgumentParser()
    for flag in ("id", "binary", "mode", "defines", "seed", "march", "repo", "out"):
        ap.add_argument("--" + flag, required=True)
    ap.add_argument("--quick", action="store_true",
                    help="only the 50 KB corpus, for smoke-testing the harness")
    args = ap.parse_args()

    corpora = CORPORA[:1] if args.quick else CORPORA

    workdir = os.path.dirname(os.path.abspath(args.binary))
    result = {
        "id": args.id,
        "defines": args.defines,
        "mode": args.mode,
        "seed": int(args.seed),
        "march": args.march,
        "host_cpu": open("/proc/cpuinfo").read().split("model name")[1]
                    .split(":")[1].split("\n")[0].strip(),
        "corpora": {},
        "roundtrip_ok": None,
        "num_models": None,
        "peak_rss_kb": 0,
        "failed": False,
        "quick": args.quick,
    }

    # Recorded before the corpus runs, so it survives even if one is killed.
    plain, stripped, packed = exe_sizes(args.binary)
    result["exe_bytes"] = plain
    result["exe_stripped_bytes"] = stripped
    result["exe_upx_bytes"] = packed

    for name, rel in corpora:
        src = os.path.join(args.repo, rel)
        comp = os.path.join(workdir, name + ".comp")
        original = os.path.getsize(src)

        elapsed, rss, rc, out = run(
            compress_cmd(args.binary, args.mode, args.repo, src, comp), workdir)
        if rc != 0 or not os.path.exists(comp):
            result["failed"] = True
            if rc == -9:
                # SIGKILL here means the OOM killer, not a codec bug. Each
                # process reserves ~19 GB of address space and resident use
                # climbs with input size; too many concurrent workers OOM.
                result["error"] = ("compress %s killed (OOM) -- reduce "
                                   "--workers" % name)
                result["oom"] = True
            else:
                result["error"] = "compress %s rc=%d: %s" % (
                    name, rc, out[-300:].decode("utf-8", "replace"))
            break

        m = NUM_MODELS_RE.search(out)
        if m:
            result["num_models"] = int(m.group(1))
        result["peak_rss_kb"] = max(result["peak_rss_kb"], rss)

        compressed = os.path.getsize(comp)
        result["corpora"][name] = {
            "original_bytes": original,
            "compressed_bytes": compressed,
            # The metric of record: bits per byte of original input, which is
            # exactly the "cross entropy" cmix prints after each run.
            "bits_per_char": round(compressed * 8.0 / original, 6),
            "compress_seconds": round(elapsed, 1),
        }

        # Round trip only the small corpus: it catches a broken ablation for
        # ~20s instead of doubling the cost of the 930 KB run.
        if name == "input":
            decomp = os.path.join(workdir, name + ".decomp")
            elapsed, rss, rc, out = run(
                decompress_cmd(args.binary, args.mode, args.repo, comp, decomp),
                workdir)
            result["peak_rss_kb"] = max(result["peak_rss_kb"], rss)
            ok = rc == 0 and os.path.exists(decomp) and \
                open(src, "rb").read() == open(decomp, "rb").read()
            result["roundtrip_ok"] = ok
            result["corpora"][name]["decompress_seconds"] = round(elapsed, 1)
            if not ok:
                result["failed"] = True
                result["error"] = "roundtrip mismatch on input"
                break

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    status = "FAILED: " + result.get("error", "") if result["failed"] else "ok"
    bpc = result["corpora"].get("input2", {}).get("bits_per_char")
    print("[%s] %s  models=%s  input2=%s bpc  rss=%.1f GB" % (
        args.id, status, result["num_models"],
        bpc if bpc is not None else "-", result["peak_rss_kb"] / 1048576.0))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
