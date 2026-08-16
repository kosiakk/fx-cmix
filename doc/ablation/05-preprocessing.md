# Preprocessing and the dictionary

The largest effect in the study by a wide margin — and the only one that
*improves* compression when present.

| Variant | CLI | Δ bits/char | Verdict |
| --- | --- | ---: | --- |
| `prep_dict` | `-c english.dic IN OUT` | **−0.1970** | improves |
| `prep_nopretrain` | same, `-DABLATE_PRETRAIN` | −0.1919 | improves |
| `prep_none` | `-n IN OUT` | +0.0001 | below noise |
| baseline | `-c IN OUT` | 0 | reference |

Three of these four needed **no code at all** — `src/runner.cpp` already
exposes the levels through its CLI. Only separating the transform from
pretraining required a flag.

## What each level removes

- **`-c dict IN OUT`** — full: the WRT dictionary transform (`encode_text` in
  `src/preprocess/preprocessor.cpp` substituting against 44 515 words, plus a
  fixed byte remap) *and* `preprocessor::Pretrain`, which feeds all 412 KB of
  the dictionary through every model before coding begins.
- **`ABLATE_PRETRAIN`** — keeps the transform, skips the pretraining. Guarded
  at both call sites in `runner.cpp`; the compressor and decompressor guards
  must match or round trips break.
- **`-n`** — no preprocessing at all.

## Predicted

`prep_dict` −0.05 to −0.15; `prep_none` +0.02 to +0.10; `prep_nopretrain`
somewhere between `prep_dict` and baseline.

## Measured, and the decomposition

**−0.1970 total, of which the transform is −0.1919 and pretraining is −0.0051.**

The transform carries **97 %** of the benefit. Pretraining on 412 KB of free
English — which `doc/fx2-cmix.md:1.7` calls "free because the decoder has the
dictionary" — adds 2.6 % as much again.

That is worth stating carefully, because the README's caveat cuts the *other*
way here: 412 KB of training data against a 930 KB corpus is proportionally
enormous compared to what it gives on enwik9, so this is pretraining's
**best case** — and it still contributes almost nothing beside the transform.
On enwik9 it should be smaller still.

## The surprise: `-c` without a dictionary is a no-op

`prep_none` and the baseline differ by 0.0001 bits/char, below noise. The
prediction of +0.02 to +0.10 was wrong, and instructively so.

The reason is structural: `preprocessor::Encode` is called with
`dictionary = NULL` when `-c` gets no dictionary argument, and the WRT stage
has nothing to substitute against. Text detection still runs and classifies
blocks, but classification alone changes nothing downstream. **The
preprocessing ladder has two rungs, not three** — with a dictionary, and
without.

This also means every model and mixer ablation in this study, which ran under
`-c IN OUT`, was effectively measured with **no preprocessing at all**. That is
a clean, well-defined baseline, and it isolates model mechanisms from
dictionary effects exactly as intended.

## Implication

The dictionary is worth **three times the entire fxcm model** (−0.1970 vs
+0.0685). For a project searching for compression wins, the ranking says the
transform and its vocabulary are the highest-leverage surface in the system —
which lines up with `doc/fx2-cmix.md:4.5`, whose one unhedged suggestion is
"replacing the dictionary *contents*, not merely its order… a genuinely
different lever and it is not obviously exhausted".

The cost side is not measured here: the dictionary is transmitted, and
`doc/fx2-cmix.md` puts that at ~100 088 bytes compressed for fx2-cmix. On
enwik9 that is trivially repaid; on a 930 KB corpus it would not be, which is
another reason to read this as direction rather than magnitude.
