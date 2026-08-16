#!/usr/bin/env python3
"""Add executable sizes to result JSONs written before that was measured.

Reads each variant's binary out of its build tree, strips and UPX-packs a copy,
and writes exe_bytes / exe_stripped_bytes / exe_upx_bytes back into the JSON.
Skips any variant whose build tree is gone or that already has the fields.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from measure import exe_sizes  # noqa: E402

BUILD_ROOT = os.environ.get("ABLATION_BUILD_ROOT", "/tmp/fx-cmix-ablation")


def main():
    updated, skipped = 0, []
    for path in sorted(glob.glob(os.path.join(HERE, "results", "*.json"))):
        with open(path) as f:
            r = json.load(f)
        if r.get("exe_upx_bytes"):
            continue
        binary = os.path.join(BUILD_ROOT, r["id"], "cmix")
        if not os.path.exists(binary):
            skipped.append(r["id"])
            continue
        plain, stripped, packed = exe_sizes(binary)
        r["exe_bytes"] = plain
        r["exe_stripped_bytes"] = stripped
        r["exe_upx_bytes"] = packed
        with open(path, "w") as f:
            json.dump(r, f, indent=2, sort_keys=True)
            f.write("\n")
        print("%-16s exe=%d stripped=%s upx=%s" % (
            r["id"], plain, stripped, packed))
        updated += 1

    print("\nupdated %d" % updated)
    if skipped:
        print("build tree gone, needs a re-run to measure: " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
