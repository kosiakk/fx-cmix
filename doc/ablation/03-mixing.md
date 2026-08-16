# The mixing stack

Seven ablations of how 490 predictions become one. Together they are the
cheapest bits in the codebase: the whole group costs under 2 KB of binary.

| Flag | Δ bits/char | Δ exe | Verdict |
| --- | ---: | ---: | --- |
| `ABLATE_MIXER_GATING` | **+0.0134** | **+16** | costs bits |
| `ABLATE_MIXER_RECURRENCE` | +0.0022 | −8 | costs bits |
| `ABLATE_MIXER_DECAY` | +0.0022 | −24 | costs bits |
| `ABLATE_SSE` | +0.0021 | −1 984 | costs bits |
| `ABLATE_LSTM_OVERRIDE` | +0.0000 | −64 | below noise |
| `ABLATE_MIXER_SKIP` | +0.0000 | −8 | below noise |
| `ABLATE_MIXER_WDECAY` | +0.0000 | −444 | below noise |

## Context gating — the best value in the codebase

**What was removed.** Every layer-0 mixer gate now reads
`manager_.zero_context_` instead of its own context. Deliberately keeps all 25
mixers and their individual learning rates, so this isolates *gating* from
*ensemble size* — a naive "delete 24 mixers" ablation would confound the two.

**Predicted** +0.02 to +0.08, low confidence, because the claim was untested.

**Measured** +0.0134 — fourth largest effect in the study, for **+16 bytes** of
binary. It is the only mechanism measured that costs nothing in code.

**Why.** Each mixer stores a weight vector per context value (capped at 10 000
distinct contexts). The gate chooses *which* weight vector mixes the experts,
so although each mixer is linear, the ensemble is gated — effectively
multiplicative. Removing the gate leaves 25 linear mixers that differ only in
learning rate, and they collapse toward doing the same job. This corroborates
`doc/fx2-cmix.md:194-197`, which argues the mixer context is the real mechanism
and "the cheap version of the conjunction layer".

It also scaled well (+0.0074 at 50 KB → +0.0134), meaning more context values
get meaningfully populated as the corpus grows.

## Cross-mixer recurrence

**Removed.** `layers_[0].SetExtraInputSize(0)` plus the `SetExtraInput` call —
layer-0 mixer *i* no longer sees the outputs of mixers 0..*i*−1 within the same
bit.

**Measured** +0.0022, above noise, for 8 bytes. A genuine if small effect: the
triangular feedback lets later mixers correct earlier ones before layer 1 sees
anything. Cheapest positive return in the study by ratio (break-even 28 KB).

## Learning-rate decay schedule

**Removed.** Constant `decay = 1` instead of the 1 M / 5 M / 25 M step tiers.

**Predicted** ±0.01 with no predicted sign, since the schedule was tuned on
enwik9 and might not apply at 1 MB.

**Measured** +0.0022 — the schedule helps, so it is not merely enwik9-specific
tuning. **But only its first two tiers were tested**: 930 KB is 7.4 M bits, so
the 25 M threshold never fires. This number is a partial measurement, and a
corpus above 3.1 MB is needed to exercise the full schedule.

## SSE — final calibration

**Removed.** `SSE::Predict` returns its input, `Perceive` no-ops, and the
object is not constructed at all — so the ~450 MB of tables and their eager
`M_Init` loop also disappear.

**Predicted** +0.01 to +0.03, citing `doc/fx2-cmix.md`'s "low single-digit
percentages" for calibration.

**Measured** +0.0021 — real, above noise, an order of magnitude under
prediction. Shelwien's two-stage SSE earns 0.13 %, not single-digit percent.
Worth keeping (break-even 7.5 MB, 1 984 bytes) but it is a polish stage, not a
pillar. The memory saving is the more striking result: 450 MB for 0.0021
bits/char is a poor RAM trade on a constrained machine.

## The three that do nothing

`ABLATE_LSTM_OVERRIDE`, `ABLATE_MIXER_SKIP` and `ABLATE_MIXER_WDECAY` all came
in at 0.0000 — predicted inert, measured inert.

- **LSTM override**: the hard bypass returning the LSTM's value directly when
  it emits exactly 0.0 or 1.0. Predicted "≈ 0" because saturation should be
  rare; confirmed. It is 64 bytes of dead-ish code.
- **Layer-1 skip connections**: re-injecting raw fxcm and LSTM predictions into
  layer 1. Both already reach layer 1 transitively through 25 layer-0 mixers,
  so the direct path adds nothing measurable.
- **Mixer weight decay**: `*= (1 − 3e-6)` every 1 024 steps. At 930 KB there is
  not enough drift for a 3-part-per-million pull to matter. Its break-even is
  444 MB — the only mechanism in the study that does not clearly repay itself
  before enwik9, though at 444 bytes the stake is trivial.

Confirming three predicted non-effects is a real result: it means the mixing
stack has no hidden load-bearing detail beyond gating.
