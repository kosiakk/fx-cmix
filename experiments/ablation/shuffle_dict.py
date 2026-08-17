#!/usr/bin/env python3
"""Write a randomly reordered copy of the word list.

The dictionary codec assigns code length by line position: lines 0-79 get a
one-byte code, 80-3919 two bytes, the rest three. The shipped list is ordered
so the most frequent words land in the cheap tiers. Shuffling keeps the exact
same vocabulary and destroys only that ordering, which isolates how much of
the dictionary's value is the word list versus the code assignment.

    ./shuffle_dict.py <in> <out> [seed]
"""
import random
import sys

src, dst = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20260817

words = open(src, "rb").read().split(b"\n")
trailing = words.pop() if words and words[-1] == b"" else None
random.Random(seed).shuffle(words)
with open(dst, "wb") as f:
    f.write(b"\n".join(words))
    if trailing is not None:
        f.write(b"\n")
print("%s -> %s: %d words, seed %d" % (src, dst, len(words), seed))
