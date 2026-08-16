# PPM and the LSTM — the coupled pair

**Flags** `-DABLATE_PPMD` (implies LSTM), `-DABLATE_LSTM` · **Δ** +0.0211 / +0.0140 · **Exe** −30 900 / −16 072 B · **Break-even** 11.7 MB / 9.2 MB

## What was removed

`AddPPMD()` builds `PPMD::PPMD` — Shelwien's mod_ppmd, order 25, a 14 000 MB
suballocator. `AddMixers()` builds `ByteMixer`, wrapping a 200-cell LSTM.

**These cannot be ablated independently in one direction.** `ByteMixer`'s only
input is PPM's 256-way byte distribution: `Predictor::Perceive` pipes
`byte_model_->BytePredict()` into `byte_mixer_->SetInput()`, and `ByteMixer` is
constructed with `num_models = 1`. Remove PPM and the LSTM has no input at all.
`src/ablation.h` therefore makes `ABLATE_PPMD` imply `ABLATE_LSTM`, and the
model counts confirm it: `ppmd` reports 488 models (−2), `lstm` reports 489 (−1).

The pair is attributed by difference.

## Predicted

`ppmd` +0.05 to +0.15; `lstm` +0.01 to +0.05, low confidence, with the
reasoning that "the LSTM sits downstream of PPM and can only re-weight
information already present", so it should be several times *smaller*.

## Measured

| | Δ bits/char |
| --- | ---: |
| Remove both (`ppmd`) | +0.0211 |
| Remove LSTM only (`lstm`) | +0.0140 |
| **PPM's own contribution (difference)** | **+0.0070** |

`lstm` was the one magnitude prediction that landed in range. The reasoning
behind it was wrong in an interesting way.

## Why

**The LSTM is worth twice PPM's own vote.** PPM contributes 0.0070 directly to
the mixer; the LSTM, whose only knowledge of the world is PPM's output,
contributes 0.0140. A downstream model that "only re-weights information
already present" doubled the value of that information.

That is not a paradox. PPM emits a full 256-way distribution each byte, but as
a mixer input it is reduced to a single bit-probability. The LSTM consumes the
whole distribution and carries state across 128 bytes of history, so it
extracts structure — sequence-level, cross-byte — that PPM's own single input
throws away. The LSTM is doing representational work on PPM's output, not
merely reweighting it.

**The LSTM also scales fastest of anything measured**: +0.0032 at 50 KB →
+0.0140 at 930 KB, 4.4×. Every other mechanism grew by well under 2×. That is
exactly the signature of a model with trainable parameters and no prior: it is
useless until it has seen data, and it is still climbing at 930 KB. Its true
enwik9 value is plausibly well above what is measured here — of everything in
this study, this is the mechanism most under-measured by a small corpus.

## Cost

Together they are the most expensive components by binary size: 47 KB of packed
executable for 0.0211 bits/char, versus fxcm's 27 KB for 0.0685. They are the
weakest payers among the large components — but both still break even around
10 MB, far inside enwik9.
