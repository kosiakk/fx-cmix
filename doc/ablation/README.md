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
beginning at `<mediawiki>`) — the only wiki-format files in the repo. Larger
corpora are supported but were not run: `fetch_corpora.sh` cuts enwik8
prefixes, and `--corpora` selects them.

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

At this build's measured 1.67 KB/s, full enwik8 is ~17 h per variant and enwik9
~170 h, against containers that were reclaimed after as little as 9 minutes and
a codec with no checkpoint/resume. That, not the network, is why the study
stops at 930 KB.

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
  the CLI already exposes its levels for free. Note this baseline turned out to
  be equivalent to no preprocessing at all — see 05-preprocessing.md.
- **Correctness**: every variant round-trips the 50 KB corpus and must
  reproduce it byte-for-byte. A variant that fails is a **bug, not a result**,
  and is labelled as such.
- **Executable size**: each variant's UPX-packed binary is measured too. The
  prize scores `S = S1 (executable) + S2 (archive)`, so a mechanism that costs
  more binary bytes than it saves archive bytes is a net loss. From that pair
  comes the **break-even corpus size** — how much input a mechanism must see
  before its savings overtake its own code. These are non-PGO `-O3` builds, so
  absolute `S1` will not match a real submission; the differences between
  variants are the point.
- **No PGO**: it changes speed, not output.
- **Pinned ISA**: all builds use `MARCH=x86-64-v3`. This is about *size*, not
  speed: `fxcmv1.cpp` picks its dot-product kernel from `__AVX2__`/`__SSE2__`,
  and under `-ffp-model=fast` a different kernel can reorder float arithmetic,
  shifting predictions and so the compressed size — at the same magnitude as
  the effects being measured. Pinning is cheap insurance for the headline
  metric.

**Compression ratio is the result here. Timing is a side channel** — useful for
spotting a mechanism that costs a lot of time for few bits, but not a criterion
this study tries to measure precisely. Wall times are not comparable across
rows: variants ran two at a time on a 4 vCPU box, and the host changed
mid-study.

## Results

**[results.md](results.md)** — master table, ranking, break-even sizes, and the
prediction scorecard. Start there.

Per-mechanism chapters, each covering what was removed, what was predicted,
what was measured, and why:

| | |
| --- | --- |
| [01-fxcm.md](01-fxcm.md) | the context-mixing engine, 439 of 490 inputs |
| [02-ppm-and-lstm.md](02-ppm-and-lstm.md) | the coupled pair, attributed by difference |
| [03-mixing.md](03-mixing.md) | gating, recurrence, skips, decay, SSE, the LSTM override |
| [04-context-models.md](04-context-models.md) | word, match, double-indirect, bracket |
| [05-preprocessing.md](05-preprocessing.md) | the dictionary — the largest effect in the study |
| [06-method-and-noise.md](06-method-and-noise.md) | noise floor, null test, and mistakes made |

Predictions were written and committed in **[predictions.md](predictions.md)**
*before* any variant finished, so they are scored honestly rather than
retrofitted. Six hits, two near, nine misses — with one systematic bias.

## Headline

Baseline is **1.5589 bits/char** on the 930 KB corpus. Removing the entire
fxcm model — 90 % of the ensemble by input count — costs **4.40 %**. Nothing
else costs more than 1.4 %. The dictionary, by contrast, *saves* **0.1970
bits/char**, three times what fxcm is worth.

This is a many-small-contributions system. No component's removal collapses it,
and no single component is hiding a large win.

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
