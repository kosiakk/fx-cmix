# Method, noise, and what went wrong

## Noise floor

Three builds differing only in `SEED`, which sets `Indirect`'s `map_offset_`
and so re-rolls hash-collision layout across the shared 128 MB map without
changing the model at all:

| Seed | bits/char (930 KB) |
| --- | ---: |
| 923 (baseline) | 1.5589 |
| 1 | 1.5595 |
| 7919 | 1.5597 |

**Noise floor: 0.0008 bits/char.** Any delta at or below this is reported as
*below noise*, not as an effect. Six variants fall there.

This matters more than it looks: without it, `mixrecur` (+0.0022) and `bracket`
(+0.0006) would read as comparable small effects. One is 2.75× the floor; the
other is under it.

## Null test

Building with no `ABLATE_*` flags must reproduce an unmodified checkout exactly.
It does: 6 155 bytes on the 50 KB corpus from both, and both report 490 models.
The guard refactor is behaviour-preserving.

## Model counts as a check

Every ablation dropped the input count by exactly the predicted amount — fxcm
439, word 25, double-indirect 11, match 10, bracket 3, PPM+LSTM 2, LSTM 1. A
mismatch would have meant a missed guard. None occurred.

## Determinism

`fxcm_check`, an independent rebuild of `-DABLATE_FXCM`, produced byte-identical
output to `fxcm` (1.6274). It was intended as a cross-host check; both landed on
the same host, so it verifies determinism rather than cross-host
reproducibility.

## Build configuration

Non-PGO, `-march=x86-64-v3` pinned. Measured against the shipped PGO+LTO+native
build on the same corpus:

| Build | input2 bytes | bits/char |
| --- | ---: | ---: |
| PGO + LTO + `-march=native` | 181 376 | 1.559012 |
| non-PGO + `x86-64-v3` | 181 364 | 1.558909 |

**12 bytes, 0.0066 %** — below the noise floor. Build configuration is
effectively neutral for the ratio, so dropping PGO cost nothing measurable
while saving several minutes per variant. The pinning was still worth keeping:
under `-ffp-model=fast` a different SIMD kernel can reorder float arithmetic,
and 12 bytes is the scale at which that shows up.

## Mistakes worth recording

Three, all mine, all with consequences:

**1. An OOM destroyed a result.** Two `run_all.sh` instances ran concurrently on
one machine — a `ps` check caught a gap between variants and I concluded the
first had exited. Each honoured `--workers 2`, so four compressions ran at once,
exhausted 15 GB, and the kernel killed baseline's `input2` pass. The failed
result then **overwrote the complete baseline**, removing the reference every
delta is measured against. Restored from git.

Fixed twice over: `measure.py` now merges corpus measurements rather than
replacing them, so results can only ever improve; and `run_all.sh` takes a
machine-wide runner lock so a second runner exits rather than silently doubling
concurrency.

**2. Detached work was invisible and got lost.** Runs launched with
`setsid nohup … & disown` are hidden from the harness, so nothing kept the
container alive and a restart silently killed everything in flight. Worse, the
stale per-variant logs left behind made a dead run look like a finished one.
Work now goes through harness-tracked background tasks.

**3. `-n` cannot decompress.** The first `prep_none` round trip failed because
the harness decompressed with `-n`. That flag is compress-only — `runner.cpp`
routes both `-c` and `-n` to `RunCompression`, and the decompressor reads
whether preprocessing was applied from the stream header. A harness bug
masquerading as a codec failure.

The infrastructure lesson: containers here get reclaimed without warning (we
saw 33 min and 9 min uptimes), so every stage was made resumable and every
result durable in git the moment it exists.

## What this study cannot tell you

- **Anything about match models.** 100 MB history, 1 % full. Below noise here.
- **The third mixer decay tier.** Fires at 25 M steps = 3.1 MB; never reached.
- **Long-range fxcm contexts.** 27 ContextMaps sized for enwik9, mostly cold.
- **Whether the ranking holds at 1 GB.** Every magnitude here is a lower bound
  for long-range mechanisms and an upper bound for the dictionary.

The natural next rung is a 5-10 MB enwik8 prefix, which crosses the 25 M-step
threshold and gives the match models something to match. `fetch_corpora.sh` and
the `--corpora` flag exist for exactly that.
