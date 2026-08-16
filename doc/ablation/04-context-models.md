# Context model families

Four ablations of the cmix-side model groups. Two matter slightly; two are
invisible at this corpus size.

| Flag | Models | Δ bits/char | Δ exe | Verdict |
| --- | ---: | ---: | ---: | --- |
| `ABLATE_WORD` | −25 | +0.0030 | −2 060 | costs bits |
| `ABLATE_DOUBLE_INDIRECT` | −11 | +0.0016 | −1 648 | costs bits |
| `ABLATE_BRACKET` | −3 | +0.0006 | −3 876 | below noise |
| `ABLATE_MATCH` | −10 | +0.0004 | −700 | below noise |

## Word models

**Removed.** `AddWord()` — 18 sparse word-context `Indirect<Nonstationary>`
models, 6 word-context `Match` models, 1 `Indirect<RunMap>`.

**Predicted** +0.03 to +0.10, on the reasoning that word contexts work at
sentence and paragraph scale and are fully engaged even at 1 MB.

**Measured** +0.0030 — over-predicted by 10×, though it is the largest of the
four and comfortably above noise. Break-even 5.4 MB.

The engagement reasoning was right; the magnitude was not. As with fxcm, 25
models overlap heavily with the other 465 — including fxcm's own word streams,
which remained present in this ablation. What is measured is the *marginal*
value of the cmix-side word models given that fxcm already models words, which
is much smaller than their standalone value would be.

## Double-indirect models

**Removed.** `AddDoubleIndirect()` — 11 `Indirect<Nonstationary>` on
indirect-hash contexts ("what usually follows the thing that usually follows
this").

**Predicted** +0.01 to +0.04. **Measured** +0.0016. Above noise, breaks even at
8.2 MB, over-predicted ~10× — the same redundancy story.

## Match models — invisible here

**Removed.** `AddMatch()` — 10 order-N hashed `Match` models.

**Predicted** +0.02 to +0.06, *with the explicit caveat* that "at 930 KB the
match models' 100 MB history is nearly empty… they should under-perform their
enwik9 value".

**Measured** +0.0004 — below the 0.0008 noise floor. No measurable effect.

**This is the study's clearest blind spot, and it was predicted.** The match
models index a 100 MB history buffer that is **1 % full** at 930 KB. Long-range
repetition — the same phrase recurring thousands of articles later — is the
thing they exist for and the thing a 930 KB prefix does not contain. Their
enwik9 value is not small; it is *unobservable here*.

**No conclusion about match models should be drawn from this study.** They are
the first thing to re-measure on a corpus of 10 MB or more.

## Bracket model

**Removed.** `AddBracket()` — the `Bracket` byte model plus the one `Direct`
and one `Indirect<Nonstationary>` on its context (3 inputs).

**Predicted** +0.005 to +0.02. **Measured** +0.0006, below noise.

Wiki markup is bracket-dense, so this is initially surprising. The likely
explanation is again redundancy: `fxcmv1.cpp` maintains its *own* bracket
context — a stack of `()`/`{}`/`[]`/`<>` with per-level distance counters —
and it was still present. The cmix-side bracket model is measuring its marginal
value on top of fxcm's, which is near zero.

It is also the worst size trade in the study: 3 876 bytes of packed binary for
an effect below noise, break-even 55.6 MB. If anything here is a candidate for
removal, it is this — but confirm on a larger corpus first, since brackets
nest at document scale.
