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

# All wiki text. input2 is a real enwik prefix starting at <mediawiki>; input
# is a mid-stream fragment. The enwik8 prefixes are fetched by
# fetch_corpora.sh and are not committed.
CORPORA = {
    "input": "prof_input/input",            # 50 KB
    "input2": "prof_input/input2",          # 930 KB
    "enwik8_5m": "experiments/ablation/corpora/enwik8_5m",    # 5 MB
    "enwik8_10m": "experiments/ablation/corpora/enwik8_10m",  # 10 MB
    "enwik8": "experiments/ablation/corpora/enwik8",          # 100 MB
}
DEFAULT_ORDER = ["input", "input2"]

# Round trips are the correctness check, and they cost as much as the
# compression. Only verify corpora at or below this size; larger runs are
# measured for size only and record roundtrip_ok as None.
ROUNDTRIP_MAX_BYTES = 1_000_000

NUM_MODELS_RE = re.compile(rb"num models (\d+)")


def run(cmd, cwd, log_path):
    """Run cmd, returning (elapsed_seconds, peak_rss_kb, returncode, output).

    Output is streamed to log_path so a multi-hour run can be watched live,
    then read back for parsing.
    """
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    start = time.monotonic()
    # Stream to a file rather than capturing into a pipe. A pipe hides
    # everything until the process exits, which on a multi-hour run means no
    # way to see whether it is progressing at all -- the output is read back
    # afterwards for parsing.
    with open(log_path, "ab") as log:
        log.write(b"\n=== %s\n" % " ".join(cmd).encode())
        log.flush()
        proc = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss is the high-water mark across all reaped children, so it only
    # tells us about this child if it exceeded every previous one. Runs are
    # ordered largest-last within a variant, and each variant is its own
    # process, so this is the peak for the variant as a whole.
    try:
        with open(log_path, "rb") as f:
            f.seek(max(0, os.path.getsize(log_path) - 65536))
            tail = f.read()
    except OSError:
        tail = b""
    return elapsed, max(after, before), proc.returncode, tail


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


def dict_path(repo):
    """Which word list to use. ABLATION_DICT overrides the shipped one, which
    is how the value of the dictionary's *ordering* gets measured: code length
    is assigned by line position (0-79 one byte, 80-3919 two, the rest three),
    so a reordered list is the same vocabulary with different code lengths."""
    return os.environ.get("ABLATION_DICT") or os.path.join(repo, "dictionary/english.dic")


def compress_cmd(binary, mode, repo, src, dst):
    if mode == "dict":
        return [binary, "-c", dict_path(repo), src, dst]
    if mode == "noprep":
        return [binary, "-n", src, dst]
    return [binary, "-c", src, dst]


def decompress_cmd(binary, mode, repo, src, dst):
    # Note "-n" is compress-only -- runner.cpp routes both -c and -n to
    # RunCompression, and the decompressor reads whether preprocessing was
    # applied out of the stream header. So everything decompresses with -d.
    if mode == "dict":
        return [binary, "-d", dict_path(repo), src, dst]
    return [binary, "-d", src, dst]


def main():
    ap = argparse.ArgumentParser()
    for flag in ("id", "binary", "mode", "defines", "seed", "march", "repo", "out"):
        ap.add_argument("--" + flag, required=True)
    ap.add_argument("--quick", action="store_true",
                    help="only the 50 KB corpus, for smoke-testing the harness")
    ap.add_argument("--corpora", default="",
                    help="comma-separated corpus names, smallest first "
                         "(default: %s)" % ",".join(DEFAULT_ORDER))
    args = ap.parse_args()

    if args.quick:
        names = DEFAULT_ORDER[:1]
    elif args.corpora:
        names = [n.strip() for n in args.corpora.split(",") if n.strip()]
    else:
        names = list(DEFAULT_ORDER)
    unknown = [n for n in names if n not in CORPORA]
    if unknown:
        print("unknown corpus name(s): %s; known: %s"
              % (", ".join(unknown), ", ".join(sorted(CORPORA))), file=sys.stderr)
        return 2
    corpora = [(n, CORPORA[n]) for n in names]

    missing = [(n, p) for n, p in corpora
               if not os.path.exists(os.path.join(args.repo, p))]
    if missing:
        print("corpus file(s) not present: %s -- run fetch_corpora.sh"
              % ", ".join("%s (%s)" % m for m in missing), file=sys.stderr)
        return 2

    workdir = os.path.dirname(os.path.abspath(args.binary))
    run_log = os.path.join(workdir, "run.log")
    result = {
        "id": args.id,
        "defines": args.defines,
        "mode": args.mode,
        "seed": int(args.seed),
        "march": args.march,
        "pgo": os.environ.get("ABLATION_PGO", "0") == "1",
        "dict_path": os.path.basename(dict_path(args.repo)) if args.mode == "dict" else None,
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
            compress_cmd(args.binary, args.mode, args.repo, src, comp),
            workdir, run_log)
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

        # Round trip only small corpora: it catches a broken ablation cheaply
        # instead of doubling the cost of every large run.
        if original <= ROUNDTRIP_MAX_BYTES:
            decomp = os.path.join(workdir, name + ".decomp")
            elapsed, rss, rc, out = run(
                decompress_cmd(args.binary, args.mode, args.repo, comp, decomp),
                workdir, run_log)
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

    # A variant's result accumulates corpus measurements across runs, so a run
    # covering only enwik8_5m adds to the existing input/input2 figures instead
    # of replacing them. This also means a failed or OOM-killed run can never
    # destroy good data -- which happened once, when an OOM overwrote a complete
    # baseline and removed the reference every delta is measured against.
    if os.path.exists(args.out):
        try:
            with open(args.out) as f:
                prev = json.load(f)
        except ValueError:
            prev = None
        if prev:
            kept = [k for k, v in prev.get("corpora", {}).items()
                    if k not in result["corpora"]]
            for k in kept:
                result["corpora"][k] = prev["corpora"][k]
            if kept:
                print("[%s] kept earlier measurements: %s"
                      % (args.id, ", ".join(sorted(kept))))
            # Preserve a previously recorded round trip when this run was too
            # large to verify one.
            if result["roundtrip_ok"] is None and prev.get("roundtrip_ok") is not None:
                result["roundtrip_ok"] = prev["roundtrip_ok"]
            for field in ("exe_bytes", "exe_stripped_bytes", "exe_upx_bytes"):
                if not result.get(field) and prev.get(field):
                    result[field] = prev[field]

    # Only a record with no usable measurement at all counts as failed.
    if result["failed"] and result["corpora"]:
        result["partial"] = True
        result["failed"] = False

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
