# fx-cmix ablation study

## Why

fx-cmix mixes **490 model outputs** and nothing in the repo says which of them
earn the bits. `doc/fx2-cmix.md:1034-1037` names this as the prior-art study's
own unclosed question:

> **What the 461 model outputs decompose into by contribution.** The count is
> printed but no per-model attribution exists in the repo, so "which of these
> tricks earns the bits" is unanswerable from source alone.

This study answers it for fx-cmix by removing one mechanism at a time and
measuring what it cost. The purpose is **to direct research attention** — a
ranking of where the bits come from — not to predict enwik9. enwik9 is the
judge; this is a map.

## Read this before reading the numbers

**The corpus is ~1 MB, and enwik9 is 1 GB.** Everything here runs on
`prof_input/input` (50 KB) and `prof_input/input2` (930 KB, a real enwik prefix
beginning at `<mediawiki>`). Those are the only wiki-format files in the repo,
and this environment's network policy blocks enwik8/enwik9 downloads.

Three consequences, stated plainly:

1. **Long-range mechanisms are under-measured.** The match models index a
   100 MB history that stays nearly empty at 1 MB. The fxcm side allocates
   ~4 GB of hash tables across 27 ContextMaps, most of which are never touched.
   The mixer learning-rate schedule has thresholds at 1 M, 5 M and 25 M steps;
   930 KB is 7.4 M bits, so the last one never fires. These mechanisms will
   look weaker here than they are on enwik9.
2. **Free side information is over-measured.** Pretraining on the 412 KB
   dictionary is worth proportionally far more against a 930 KB corpus than
   against 1 GB.
3. **So read the ranking, not the magnitudes.** A delta here says "this
   mechanism is load-bearing", not "this mechanism is worth X bytes on enwik9".

**Deltas below the noise floor are not results.** The floor is the spread
across three RNG seeds. `SEED` sets `Indirect`'s `map_offset_`, so changing it
re-rolls hash-collision layout without changing the model at all; any effect
smaller than that spread is indistinguishable from collision luck.

## Method

Each variant is one `-DABLATE_*` flag defined in `src/ablation.h`, which gates
a `HAS_<NAME>` constant. With no flags the build is byte-identical to an
unmodified checkout — verified against a build of unmodified `HEAD`, both
producing 6155 bytes on `prof_input/input` and both reporting 490 models.

Variants are compile-time flags on `main`, not branches, so the whole matrix
lives in one commit, re-runs after any harness change, and composes (the
coupled PPM+LSTM case is just two flags).

- **Metric**: bits per character, `compressed_bytes * 8 / original_bytes` —
  the same "cross entropy" `cmix -c` prints after each run.
- **Configuration**: model and mixer ablations run `cmix -c IN OUT` (text
  detection on, dictionary off). Preprocessing is studied separately, because
  the CLI already exposes three levels for free.
- **Correctness**: every variant round-trips the 50 KB corpus and must
  reproduce it byte-for-byte. A variant that fails is a **bug, not a result**,
  and is labelled as such.
- **No PGO**: it changes speed, not output.
- **Pinned ISA**: all builds use `MARCH=x86-64-v3`. `fxcmv1.cpp` picks its
  dot-product kernel from `__AVX2__`/`__SSE2__`, and a different kernel means
  different float rounding and so a different compressed size. This was not
  hypothetical — the host backing this session changed from a 2.10 GHz to a
  2.80 GHz Xeon mid-study.

**Wall times are indicative only** and should not be compared across rows: the
host changed mid-study and variants ran two at a time on a 4 vCPU box.

## Results

See `results.md` for the master table, and the per-mechanism chapters for what
each removal did and why.

Predictions were written and committed in `predictions.md` **before** any
variant finished, so they can be scored honestly rather than retrofitted.

## Reproducing

```bash
cd experiments/ablation
./run_all.sh --workers 2          # the whole matrix
./run_all.sh --only sse,mixgate   # selected variants
python3 collect.py                # regenerate the master table
```

`--workers 2` is a memory limit, not a CPU one. Each process reserves ~19 GB of
address space (PPM 14.7 GB + fxcm tables ~4 GB + SSE ~450 MB), nearly all of it
lazily, and resident use reaches ~5.5 GB on the 930 KB corpus. Three concurrent
variants exhausted 15 GB and the kernel killed one mid-run.
