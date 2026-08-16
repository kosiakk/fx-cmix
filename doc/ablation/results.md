# Results

Complete matrix, 21 variants, no failures and no round-trip failures.
Baseline is **1.5589 bits/char** on the 930 KB corpus.

Positive Δ means the ablation cost bits, i.e. the mechanism was earning them.
Read [README.md](README.md) for the method and the caveats first, and
[predictions.md](predictions.md) for what was predicted before the run.

| Variant | Group | Models | input 0.05 MB | Δ | input2 0.93 MB | Δ | UPX exe | Δ exe | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `baseline` | baseline | 490 | 0.9838 | +0.0000 | 1.5589 | +0.0000 | 126272 | +0 | reference |
| `seed7919` | noise | 490 | 0.9838 | +0.0000 | 1.5597 | +0.0008 | 126272 | +0 | below noise |
| `seed1` | noise | 490 | 0.9841 | +0.0003 | 1.5595 | +0.0006 | 126272 | +0 | below noise |
| `fxcm` | ensemble | 51 | 1.0425 | +0.0587 | 1.6274 | +0.0685 | 99328 | -26944 | costs bits |
| `ppmd` | ensemble | 488 | 0.9955 | +0.0117 | 1.5800 | +0.0211 | 95372 | -30900 | costs bits |
| `lstm` | ensemble | 489 | 0.9870 | +0.0032 | 1.5730 | +0.0140 | 110200 | -16072 | costs bits |
| `word` | ensemble | 465 | 0.9865 | +0.0027 | 1.5620 | +0.0030 | 124212 | -2060 | costs bits |
| `dindirect` | ensemble | 479 | 0.9859 | +0.0021 | 1.5605 | +0.0016 | 124624 | -1648 | costs bits |
| `bracket` | ensemble | 487 | 0.9835 | -0.0003 | 1.5595 | +0.0006 | 122396 | -3876 | below noise |
| `match` | ensemble | 480 | 0.9836 | -0.0002 | 1.5593 | +0.0004 | 125572 | -700 | below noise |
| `mixgate` | mixing | 490 | 0.9911 | +0.0074 | 1.5723 | +0.0134 | 126288 | +16 | costs bits |
| `mixrecur` | mixing | 490 | 0.9851 | +0.0013 | 1.5612 | +0.0022 | 126264 | -8 | costs bits |
| `mixdecay` | mixing | 490 | 0.9838 | +0.0000 | 1.5611 | +0.0022 | 126248 | -24 | costs bits |
| `sse` | mixing | 490 | 0.9852 | +0.0014 | 1.5610 | +0.0021 | 124288 | -1984 | costs bits |
| `lstmover` | mixing | 490 | 0.9844 | +0.0006 | 1.5590 | +0.0000 | 126208 | -64 | below noise |
| `mixskip` | mixing | 490 | 0.9841 | +0.0003 | 1.5589 | +0.0000 | 126264 | -8 | below noise |
| `mixwdecay` | mixing | 490 | 0.9838 | +0.0000 | 1.5589 | +0.0000 | 125828 | -444 | below noise |
| `prep_none` | preprocess | 490 | 0.9836 | -0.0002 | 1.5590 | +0.0001 | 126272 | +0 | below noise |
| `prep_nopretrain` | preprocess | 490 | 0.7714 | -0.2124 | 1.3670 | -0.1919 | - | - | **improves** |
| `prep_dict` | preprocess | 490 | 0.7637 | -0.2201 | 1.3619 | -0.1970 | 126272 | +0 | **improves** |
| `fxcm_check` | integrity | 51 | 1.0425 | +0.0587 | 1.6274 | +0.0685 | 99328 | -26944 | costs bits |

### Break-even corpus size

_Savings measured on `input2`._

How much input a mechanism must see before the bytes it saves exceed the bytes its code costs in the packed executable.

| Mechanism | Exe cost (B) | Saves (bits/char) | Breaks even at |
| --- | ---: | ---: | ---: |
| `mixrecur` | 8 | 0.0022 | 28.5 KB |
| `mixdecay` | 24 | 0.0022 | 89.0 KB |
| `mixskip` | 8 | 0.0000 | 1.9 MB |
| `fxcm` | 26944 | 0.0685 | 3.1 MB |
| `fxcm_check` | 26944 | 0.0685 | 3.1 MB |
| `word` | 2060 | 0.0030 | 5.4 MB |
| `sse` | 1984 | 0.0021 | 7.5 MB |
| `dindirect` | 1648 | 0.0016 | 8.2 MB |
| `lstm` | 16072 | 0.0140 | 9.2 MB |
| `ppmd` | 30900 | 0.0211 | 11.7 MB |
| `lstmover` | 64 | 0.0000 | 12.2 MB |
| `match` | 700 | 0.0004 | 13.3 MB |
| `bracket` | 3876 | 0.0006 | 55.6 MB |
| `mixwdecay` | 444 | 0.0000 | 444.0 MB |

enwik9 is 1 000 MB, so anything breaking even well below that earns its place; anything near or above it is a candidate for removal on a size-scored benchmark.

Noise floor (seed replicate spread on `input2`): **0.0008 bits/char**.

Hosts: Intel(R) Xeon(R) Processor @ 2.80GHz

Integrity check on `input2`: fxcm 1.6274 vs fxcm_check 1.6274 -- identical
Built on Intel(R) Xeon(R) Processor @ 2.80GHz and Intel(R) Xeon(R) Processor @ 2.80GHz. Same host, so this checks determinism rather than cross-host reproducibility.

## Ranking

Everything above the noise floor, largest first:

| Rank | Mechanism | Δ bits/char | Relative |
| ---: | --- | ---: | ---: |
| 1 | `fxcm` | +0.0685 | 4.40 % |
| 2 | `ppmd` (PPM + LSTM together) | +0.0211 | 1.35 % |
| 3 | `lstm` | +0.0140 | 0.90 % |
| 4 | `mixgate` | +0.0134 | 0.86 % |
| 5 | `word` | +0.0030 | 0.19 % |
| 6 | `mixrecur` | +0.0022 | 0.14 % |
| 7 | `mixdecay` | +0.0022 | 0.14 % |
| 8 | `sse` | +0.0021 | 0.13 % |
| 9 | `dindirect` | +0.0016 | 0.10 % |

Below the 0.0008 noise floor, i.e. no measurable effect at this scale:
`bracket`, `match`, `lstmover`, `mixskip`, `mixwdecay`, `prep_none`.

Separately, and far larger than any of them, the dictionary **improves**
compression by **0.1970 bits/char** — three times the entire fxcm model.

## The five findings that matter

**1. No single mechanism is close to load-bearing on its own.** Removing
fxcm — 439 of 490 inputs, the headline change over fast-cmix — costs 4.4 %.
Everything else is under 1.4 %. This is a many-small-contributions system, and
that is the central result: there is no component whose removal collapses it,
and equally no single place where a large win is waiting.

**2. The LSTM earns more than the PPM it reads from.** The two are coupled —
`ByteMixer`'s only input is PPM's 256-way byte distribution — so they were
ablated as a pair and separately. Removing both costs 0.0211; removing only
the LSTM costs 0.0140. **PPM's own direct contribution is the difference:
0.0070, half of what the LSTM extracts from it.** A 200-cell LSTM reading
PPM's output is worth twice PPM's own vote in the mixer. The LSTM also grew
4.4× from the 50 KB corpus to the 930 KB one (+0.0032 → +0.0140), by far the
steepest scaling of anything measured, which is what a neural model that needs
data to train should look like.

**3. Mixer context gating is the best value in the codebase.** Pointing all 25
layer-0 gates at a constant context — same mixer count, same learning rates,
only the gating removed — costs 0.0134 bits/char, fourth largest in the study.
It changes the packed binary by **+16 bytes**. Every other mechanism trades
code size for bits; this one is free. It corroborates `doc/fx2-cmix.md:194-197`,
which argues the mixer *context* is the real mechanism because it makes a
linear mixer effectively multiplicative.

**4. The dictionary dwarfs the models, and it is nearly all transform.** Full
preprocessing is worth −0.1970 bits/char. Splitting it: the WRT transform alone
accounts for **−0.1919**, and pretraining the models on the 412 KB dictionary
adds only **−0.0051** on top. Note the caveat in README — 412 KB of free
training data against a 930 KB corpus flatters pretraining, and it still
contributes almost nothing next to the transform.

**5. `-c` without a dictionary does nothing at all.** `prep_none` (`-n`, no
preprocessing) and the baseline (`-c`, text detection on, no dictionary) differ
by 0.0001 bits/char — below noise. The WRT stage is a no-op without a
dictionary to substitute against, so the preprocessing ladder has two rungs,
not three.

## What this corpus cannot see

`match` (+0.0004) and `bracket` (+0.0006) sit at the noise floor. For the match
models this is expected and explains itself: they index a 100 MB history that
is 1 % full at 930 KB. Their enwik9 value is invisible here, and no conclusion
about them should be drawn from this study. The mixer schedule's third
threshold (25 M steps = 3.1 MB of input) is likewise never reached, so
`mixdecay`'s +0.0022 reflects only its first two tiers.

These are the specific reasons the README says to read the ranking, not the
magnitudes.

## Is anything not worth its size?

Break-even (above) answers the question directly: with one exception every
mechanism repays its own code well inside enwik9's 1 GB, most of them inside
15 MB. `bracket` (55.6 MB) and `mixwdecay` (444 MB) are the laggards, and both
are cheap enough in absolute terms — 3 876 and 444 bytes — that removing them
would be noise on `S1`.

**So: nothing here is dead weight for the prize.** The interesting spread is in
the margins, not in anything deletable. `mixgate` is the standout at zero
binary cost, and `lstm`/`ppmd` are the weakest payers among the large
components — together 47 KB of packed binary for 0.0211 bits/char.

## Prediction scorecard

Predictions were committed in `predictions.md` before any variant finished.

| Predicted | Outcome |
| --- | --- |
| `lstm` +0.01 to +0.05 | **hit** — +0.0140 |
| `mixdecay` ±0.01, sign unknown | **hit** — +0.0022 |
| `mixskip` below noise | **hit** |
| `mixwdecay` below noise | **hit** |
| `lstmover` ≈ 0 | **hit** |
| `prep_nopretrain` between `prep_dict` and baseline | **hit** |
| `mixgate` +0.02 to +0.08 | near — +0.0134, just under |
| `mixrecur` +0.005 to +0.02 | near — +0.0022, just under |
| `fxcm` +0.30 to +0.60 | **miss** — +0.0685, over-predicted 4-9× |
| `ppmd` +0.05 to +0.15 | **miss** — +0.0211 |
| `word` +0.03 to +0.10 | **miss** — +0.0030, over-predicted 10× |
| `match` +0.02 to +0.06 | **miss** — +0.0004, below noise |
| `dindirect` +0.01 to +0.04 | **miss** — +0.0016 |
| `sse` +0.01 to +0.03 | **miss** — +0.0021 |
| `bracket` +0.005 to +0.02 | **miss** — +0.0006, below noise |
| `prep_none` +0.02 to +0.10 | **miss** — +0.0001, below noise |
| `prep_dict` −0.05 to −0.15 | **miss** — −0.1970, under-predicted |

Six hits, two near, nine misses — and the misses share one direction. **I
over-estimated almost every magnitude, typically by 5-10×**, while getting the
*ordering* broadly right and the "this will do nothing" calls exactly right.
The single systematic error was expecting individual mechanisms to be worth
percent-scale amounts when they are worth tenth-of-a-percent amounts. The one
under-prediction is the dictionary, the only thing in the study that is
genuinely large.

Two of the misses were anticipated in `predictions.md`'s own falsification
section: `match` coming out near zero, and `prep_dict` beating its range. Both
happened, for the stated reasons.
