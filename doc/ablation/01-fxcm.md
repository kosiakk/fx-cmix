# fxcm — the context-mixing engine

**Flag** `-DABLATE_FXCM` · **Models removed** 439 of 490 · **Δ** +0.0685 bits/char (4.40 %) · **Exe** −26 944 B · **Break-even** 3.1 MB

## What was removed

`AddFXCM()` (`src/predictor.cpp`), which constructs the `FXCM` model wrapping
`fxcmv1::Predictor` — 3 000 lines containing 27 ContextMaps (~4 GB of hash
tables), 8 SmallStationaryContextMaps, its own match model, 9 internal mixers
and a 6-APM chain. It supplies 439 layer-0 inputs.

Removing it also removes one of the two auxiliary skip connections into layer 1
and one of the two terms in `auxiliary_context_`, both handled by
`AUX_AVERAGED` / `AUX_SKIP_INPUTS` in `src/ablation.h`.

## Predicted

+0.30 to +0.60 bits/char, high confidence. This was the headline change fx-cmix
made over fast-cmix, and it is 90 % of the ensemble by input count.

## Measured

+0.0685 bits/char — **4 to 9× smaller than predicted**, and the largest single
miss in the study. Consistent across both corpora (+0.0587 at 50 KB), so it is
not a small-corpus artifact.

## Why

The prediction confused *input count* with *information*. 439 inputs is 90 % of
the ensemble, but the remaining 51 — PPM, the LSTM, 16 match models, 30
indirect models, the bracket model — cover much of the same ground. A
context-mixing ensemble is deliberately redundant: mixers learn to route around
any single missing expert, so no expert's marginal value approaches its share
of the inputs.

That redundancy is the real finding. It also bounds what fxcm's *replacement*
could ever be worth: if removing 439 experts costs 4.4 %, no rearrangement of
them wins more than that.

The 27 ContextMaps are sized for enwik9 and are mostly untouched at 930 KB, so
this figure is a floor. fxcm's advantage should grow with corpus size — the
50 KB → 930 KB trend (+0.0587 → +0.0685) is consistent with that, but shallow.

## Coupling

`fxcm_check`, an independent rebuild of the same flags, produced byte-identical
output (1.6274), confirming the build is deterministic.
