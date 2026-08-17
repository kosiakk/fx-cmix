#!/usr/bin/env python3
"""Reorder the word list by corpus statistics, keeping the vocabulary identical.

    ./rank_dict.py <corpus> <dict-in> <dict-out> [freq|savings]

Code length depends only on line position (0-79 one byte, 80-3919 two, the
rest three), so reordering the same words changes only which of them get cheap
codes. That makes ordering measurable on its own.

Counting matches the codec's tokenizer (`dictionary.cpp:75-137`): a word is a
maximal run of [A-Za-z], lowercased. The mixed-case split rule is not
reproduced, which is why this is an approximation.

Two rankings:

  freq     plain occurrence count -- the naive answer, and the one worth
           testing against two decades of hand curation.
  savings  count * (len(word) - code_len). What actually matters is bytes
           saved, not occurrences: a 12-letter word in the one-byte tier saves
           11 bytes per hit, a 3-letter word saves 2. Tier assignment depends
           on rank and rank depends on tier, so this iterates to a fixed point.

Words absent from the corpus keep their original relative order and go last.
"""

import collections
import re
import sys

TIERS = ((80, 1), (3920, 2))          # (upper bound exclusive, code bytes)


def code_len(rank):
    for bound, n in TIERS:
        if rank < bound:
            return n
    return 3


def main():
    corpus, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    key = sys.argv[4] if len(sys.argv) > 4 else "freq"

    words = open(src, "rb").read().decode("utf-8", "replace").split("\n")
    trailing = words.pop() == "" if words else False
    original = {w: i for i, w in enumerate(words)}

    counts = collections.Counter()
    with open(corpus, "rb") as f:
        blob = f.read()
    for m in re.finditer(rb"[A-Za-z]+", blob):
        counts[m.group(0).lower().decode("ascii")] += 1

    present = [w for w in words if counts.get(w)]
    absent = [w for w in words if not counts.get(w)]

    if key == "freq":
        present.sort(key=lambda w: (-counts[w], original[w]))
    else:
        # Fixed-point: rank by savings, recompute code lengths, repeat.
        present.sort(key=lambda w: (-counts[w], original[w]))
        for _ in range(20):
            pos = {w: i for i, w in enumerate(present)}
            ordered = sorted(
                present,
                key=lambda w: (-counts[w] * max(0, len(w) - code_len(pos[w])),
                               original[w]))
            if ordered == present:
                break
            present = ordered

    out = present + absent
    assert sorted(out) == sorted(words), "vocabulary changed"
    with open(dst, "wb") as f:
        f.write("\n".join(out).encode("utf-8"))
        if trailing:
            f.write(b"\n")

    covered = sum(counts[w] for w in present)
    tier1 = sum(counts[w] for w in out[:80])
    print("%s -> %s [%s]" % (src, dst, key))
    print("  %d words, %d seen in corpus, %d unseen (kept last)"
          % (len(out), len(present), len(absent)))
    print("  corpus occurrences covered: %d" % covered)
    print("  share of covered occurrences in the 1-byte tier: %.1f%%"
          % (100.0 * tier1 / covered if covered else 0))
    print("  first 8: %s" % " ".join(out[:8]))


if __name__ == "__main__":
    main()
