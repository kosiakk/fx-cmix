# Predictions, recorded before the results

Written and committed before any variant finished, so the predictions are
falsifiable rather than retrofitted. Each is a direction, a rough magnitude on
`prof_input/input2` (930 KB) in bits/char, and the reasoning behind it.

Baseline for reference: **0.9838 bits/char** on `prof_input/input` (50 KB).
Positive delta = the ablation costs bits, i.e. the mechanism was earning them.

| Variant | Predicted Δ bits/char | Confidence |
| --- | --- | --- |
| `fxcm` | +0.30 to +0.60 | high |
| `word` | +0.03 to +0.10 | medium |
| `ppmd` (with LSTM) | +0.05 to +0.15 | medium |
| `match` | +0.02 to +0.06 | medium |
| `mixgate` | +0.02 to +0.08 | low |
| `dindirect` | +0.01 to +0.04 | medium |
| `sse` | +0.01 to +0.03 | medium |
| `lstm` alone | +0.01 to +0.05 | low |
| `bracket` | +0.005 to +0.02 | medium |
| `mixrecur` | +0.005 to +0.02 | low |
| `mixdecay` | ±0.01, sign unknown | low |
| `mixskip` | below noise | low |
| `mixwdecay` | below noise | low |
| `lstmover` | ≈ 0 | high |
| `prep_dict` | **−0.05 to −0.15** | medium |
| `prep_nopretrain` | between `prep_dict` and baseline | medium |
| `prep_none` | +0.02 to +0.10 | medium |

## Reasoning

**`fxcm` should dominate.** It supplies 439 of the 490 layer-0 inputs and is
the headline change fx-cmix made over fast-cmix. Removing it leaves 51 inputs
and also strips one of the two auxiliary skip connections. This is less an
ablation than a different compressor, and it is included mainly to bound the
scale — if anything else comes within an order of magnitude of it, that is the
surprise.

**PPM and the LSTM are the coupled pair.** PPM is a strong standalone model
that predicts whole bytes rather than bits, so it contributes information the
context-mixing side does not have. The LSTM sits downstream of PPM and only
sees PPM's byte distribution, so it can only re-weight information already
present. I expect `lstm` alone to be small and `ppmd` (which removes both) to
be several times larger; the difference is PPM's own contribution.

**Word models over match models.** At 930 KB the match models' 100 MB history
is nearly empty and long-range repetition is rare, so match models should
under-perform their enwik9 value. Word contexts, by contrast, work at sentence
and paragraph scale and are fully engaged even on 1 MB.

**Mixer gating is the interesting one.** `doc/fx2-cmix.md:194-197` argues the
mixer *context* is the real mechanism — it makes a linear mixer effectively
multiplicative. `mixgate` tests that directly, holding mixer count and learning
rates fixed and only removing the gates' ability to specialise. Confidence is
low precisely because the claim is untested; a large effect would corroborate
it, a small one would suggest the gating mostly duplicates what the 25
different learning rates already provide.

**SSE should be small but real.** The same document calls final-stage
calibration "cheap and routinely worth low single-digit percentages". Note the
ablation also removes ~450 MB of tables and their eager init, so expect time
and memory to drop alongside any size change — don't read the speedup as a win.

**Preprocessing should be the one clear improvement.** `prep_dict` adds the WRT
dictionary transform *and* pretrains every model on 412 KB of English before
coding starts. On a 930 KB input, 412 KB of free training data is enormous
relative to the corpus — proportionally far more help than it gives on enwik9,
which is a reason to distrust the magnitude while trusting the sign.
`prep_nopretrain` separates the transform from the free training data.

**Three predicted to be inert.** `lstmover` fires only when the LSTM emits
exactly 0.0 or 1.0, which should be rare. `mixwdecay` is a 3e-6 pull applied
every 1024 steps. `mixskip` removes two of 27 layer-1 inputs that are already
present transitively through the layer-0 mixers. If any of these turns out to
matter, that is a genuinely interesting result.

**`mixdecay` has no predicted sign.** Both the 1M and 5M step thresholds are
crossed on a 930 KB input (7.4 M bits), so the schedule is live. Removing it
keeps the learning rate high, which helps if the mixers are still adapting and
hurts if they should be settling. The schedule was presumably tuned on enwik9,
where 25 M steps is early; on 1 MB the tuning may simply not apply.

## What would falsify the framing

The study assumes deltas measured at 1 MB rank mechanisms the same way they
would at 1 GB. Two results would undermine that: `match` coming out near zero
(consistent with its history being empty, so its enwik9 value is invisible
here), or `prep_dict` improving by far more than predicted (consistent with
free training data being disproportionately valuable at small scale). Both are
expected to some degree, which is why the caveat belongs in the README rather
than being discovered later.
