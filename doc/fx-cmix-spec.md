# fx-cmix: what we know about this codebase

**Status: EVERGREEN — this file is the record.** Findings established by
reading the source or by measurement go here, not into chat transcripts. Each
claim carries either a `file:line` reference or the number it was measured at,
and claims that are uncertain say so.

Companion documents: `doc/fx2-cmix.md` is a study of the *successor* project
and its line references do not apply here. `doc/ablation/` holds the ablation
study's tables and per-run predictions.

---

## 1. Architecture, as it actually is

`Predictor::Predictor` (`src/predictor.cpp:13-33`) is a seven-call switchboard:
`AddBracket`, `AddFXCM`, `AddPPMD`, `AddWord`, `AddMatch`,
`AddDoubleIndirect`, `AddMixers`. That structure is why per-mechanism ablation
is cheap here.

**490 model outputs** reach the first mixer layer (`GetNumModels()`,
`src/predictor.cpp:35-53`; printed at startup):

| Family | Inputs | Added by |
| --- | ---: | --- |
| fxcm (`fxcmv1.cpp`) | 439 | `AddFXCM` |
| indirect non-stationary | 30 | word ×18, double-indirect ×11, bracket ×1 |
| match | 16 | word ×6, order-N ×10 |
| bracket, direct, indirect-run, PPM, LSTM | 1 each | — |

Above that: 25 context-gated layer-0 mixers, one layer-1 mixer, and Shelwien's
two-stage SSE (`src/mixer/sse.cpp`).

### 1.1 Things that are *not* here

These exist in fx2-cmix and are described in `doc/fx2-cmix.md`, but **fx-cmix
has none of them**. Confirmed by grep over `src/`:

- **No stemmer.** No Porter2, no word-type tags, no `lastWT`, no four filtered
  word streams. (The `isTemp` hits in `fxcmv1.cpp` are wiki-template parsing.)
- **No reverse-dictionary buffer.** fxcm never sees decoded plaintext.
- **fxcm never opens the word list.** Only `src/preprocess/preprocessor.cpp:155`
  constructs a `Dictionary`. `fxcmv1.cpp:70` has `//#define TEXTMODE`
  commented out, which selects the dictionary-processed-input path — but that
  only means fxcm expects coded bytes, not that it knows what they mean.

**Consequence:** a replacement vocabulary has exactly one integration point,
`Dictionary`, with nothing downstream to keep in sync.

### 1.2 Coupling that matters

- **PPM → LSTM.** `ByteMixer` has a single input: PPM's 256-way byte
  distribution (`src/predictor.cpp`, `Perceive`; `byte-mixer.cpp`,
  `num_models_ == 1`). Removing PPM removes the LSTM's only information
  source, so `ABLATE_PPMD` implies `ABLATE_LSTM` (`src/ablation.h`). Ablating
  the LSTM alone, and both together, brackets PPM's own contribution.
- **fxcm and LSTM feed `auxiliary_context_`** (a mixer gate) and are
  re-injected into layer 1 as skip connections.

### 1.3 Bugs found and fixed

- **`mmap_to_disk = true` crashes.** PPM periodically `munmap`s and remaps its
  backing file every 20000 bytes; the kernel need not return the same address,
  leaving stale pointers. Default is now `false` (`src/models/ppmd.cpp:33`).
  It also preallocates a file sized for a full enwik9 run regardless of input.
- **`auxiliary_size_` was assigned after it was read.** It was set at the end
  of the constructor, but `AddMixers()` had already used its default
  initializer; and it served as both the layer-1 extra-input count and the
  averaging divisor. Split into `AUX_SKIP_INPUTS` and `AUX_AVERAGED`.

---

## 2. The dictionary codec

`src/preprocess/dictionary.cpp`. This is the highest-value component in the
system and the least documented, so it gets the most detail.

### 2.1 Code assignment is positional, in three tiers

`dictionary.cpp:45-62`. Code length depends **only on line number**:

| Lines | Bytes | Encoding |
| --- | ---: | --- |
| 0 – 79 | 1 | `0x80 + i` |
| 80 – 3 919 | 2 | `0xD0 + …`, `0x80 + …` |
| 3 920 – 44 879 | 3 | `0xF0 + …`, `0xD0 + …`, `0x80 + …` |

Tiers occupy distinct leading-byte ranges, so a model reading the first byte
knows the tier immediately. The shipped list has 44 515 words in 411 996 bytes.

It is **not** a varint — the tier is fixed by position, not by value.

### 2.2 What can be a token

`Dictionary::Encode` (`dictionary.cpp:75-137`) fixes the tokenizer:

- A word is a maximal run of `[A-Za-z]`, **lowercased** on entry. Any other
  byte ends it.
- Mixed case forces a boundary (lowercase→uppercase, or 2+ uppercase→lowercase).
- Case travels out-of-band as markers emitted *before* the word: `0x40`
  capitalized, `0x07` all-caps, `0x06` end-of-upper-run, `0x0C` escape.
- Words longer than `longest_word_` are force-broken.

**So vocabulary entries must be lowercase `[a-z]+` strings matching whole
alphabetic runs.** Standard BPE vocabularies do not satisfy this: subword
markers (`##ing`, `Ġthe`), pieces spanning punctuation or digits, and
case-bearing tokens are all unrepresentable.

`EncodeSubstring` (`dictionary.cpp`) gives limited subword capability: for
words longer than 7 characters it tries the longest suffix ≥ 7 chars in the
map, else the longest prefix. One affix only — it cannot carry a general merge
table.

### 2.3 The dictionary is transmitted, and already compressed

`build_and_construct_comp.sh` compresses the word list **with cmix itself**:
411 996 → ≈ 100 088 bytes, and that is what counts toward `S1`. Any
alternative vocabulary must beat **~100 KB after cmix compression**, not the
raw 412 KB.

---

## 3. Measured results

All on `prof_input/input2` (930 723 bytes, a real enwik prefix). Build details
in `experiments/ablation/results/*/`.

### 3.1 The transform does about half the work

With **every model ablated**, output size *is* the transformed stream, which
makes this an exact measurement rather than an estimate:

| Configuration | bytes out | bits/char |
| --- | ---: | ---: |
| No models, no dictionary | 930 767 | **8.0004** |
| No models, shuffled word list | 688 847 | **5.9210** |
| No models, shipped word list | 552 447 | **4.7485** |
| Full system (490 models) | 158 479 | **1.3621** |

The 8.0004 confirms the ablation framework composes correctly: `models=0`,
p = 0.5 on every bit, output = input + 44 bytes of header. No crash. There is
**no order-0 fallback** — nothing counts symbols at all.

Sequential decomposition of the 6.6379 bits/char achieved:

- **WRT transform alone: 3.2515 (49.0%)**
- **The entire 490-model ensemble: 3.3864 (51.0%)**

Of the transform's 3.2515:

- **having the vocabulary: 2.0790 (64%)**
- **having it in frequency order: 1.1724 (36%)**

Ordering alone is worth **17.7% of the whole compression budget** and about
**15× the largest single model ablation**. Caveat: random shuffling is the
worst case, not a neutral one — it anti-correlates code length with frequency.
The honest bracket is "hand-curated order" against "no ordering information",
not against a plausible alternative such as corpus-frequency sorting. That
comparison is **not yet run**.

### 3.2 Leave-one-out deltas do not sum to the total, and cannot

Sum of 15 marginal deltas: **0.1866 bits/char = 2.8%** of the compression
achieved. The other **97.2% is redundancy**: with 490 inputs the mixer
re-weights and the survivors reconstruct nearly everything a removed model
knew, so shared information is claimed by no single ablation. This is a
property of the ensemble, not a measurement error.

The dictionary alone (0.1968) is worth **more than every model and mixer
mechanism combined**.

Decomposing the remainder needs a different design: leave-one-in (standalone
power; sums above the total), cumulative ablation (sums exactly, order
dependent), or sampled Shapley values.

### 3.3 The dictionary is an ablation axis, not a setting

Deltas differ by arm, and one mechanism moves the *other* way:

| Mechanism | Δ with dict | Δ without dict | Shift |
| --- | ---: | ---: | ---: |
| `fxcm` | +0.0764 | +0.0685 | **+0.0078** |
| `ppmd` | +0.0096 | +0.0211 | −0.0115 |
| `lstm` | +0.0077 | +0.0140 | −0.0064 |
| `mixgate` | +0.0073 | +0.0134 | −0.0061 |
| `word` | +0.0007 | +0.0030 | −0.0023 |

**fxcm is the only mechanism that earns more with the dictionary** —
consistent with its v16 path being written for the coded stream. Everything
else shrinks: those mechanisms were partly re-deriving what WRT removes.

Four mechanisms fall to noise once the dictionary is on: `match`, `bracket`,
`dindirect`, and `word` is marginal at +0.0007.

**`cmix -c IN OUT` without a dictionary argument is a no-op**: 1.5589 against
`-n`'s 1.5590. The WRT transform needs a word list to code against.

### 3.4 Best value per byte of source

`mixgate` — pointing all 25 layer-0 mixer gates at a constant context — costs
**+0.0073 bits/char for 784 bytes** of packed binary. Statistically level with
the LSTM at 1/25th the code. Context gating is the best ratio in the ensemble.

### 3.5 Noise floors and build sensitivity

- Dictionary arm: **0.0003 bits/char** (seed spread). No-dictionary arm:
  **0.0008**. The coded stream is more predictable, so effects stand clearer.
- `SEED` changes `Indirect`'s `map_offset_`, re-rolling hash-collision layout
  without changing the model — the right noise proxy.
- **PGO and `-march` barely matter for ratio**: PGO+LTO+`native` versus
  non-PGO+`x86-64-v3` differs by 12 bytes on 181 KB (0.007%), well below both
  noise floors. Pin `-march` anyway when pooling results across machines.
- One completed enwik8 run (nodict, no PGO): `lstm` ablation at **1.305148**
  bits/char, 100 000 000 → 16 314 354 bytes.

---

## 4. Operational facts

- **Throughput** (C3, non-PGO, `-march=native`): ~3.5 KB/s in nodict mode.
  Dict mode is **~2.1× faster** (258 s vs 544 s on input2) because the coded
  stream is shorter. enwik8 ≈ 7.7 h nodict, ~3.7 h dict; enwik9 ≈ 77 h nodict,
  ~38 h dict.
- **Memory is the parallelism limit, not CPU.** cmix is single-threaded per
  run. Reservations: PPM 14.7 GB, fxcm tables ~4 GB, SSE ~450 MB, mostly lazy.
  Resident: ~5.5 GB at 930 KB, ~6.8 GB at enwik8, ~0.2 GB with all models
  ablated. Budget ~20 GB per concurrent run.
- **cmix has no checkpoint/resume.** An interrupted run restarts from zero,
  which rules out multi-hour runs on preemptible or reclaimable machines.
- **Progress**: cmix writes `<percent> <output_bytes>` to `./progress.log` in
  its working directory (`src/runner.cpp:160`). That is the only live signal;
  stderr is a carriage-return bar. `experiments/ablation/status.sh` decodes it.

---

## 5. Open questions

1. **Does hand curation beat naive frequency sorting?** Sorting the same
   44 515 words by their enwik8 frequency and re-running the null build would
   answer it in ~2 minutes. Not yet run. (`doc/fx2-cmix.md` open question #3.)
2. **Do `match` and `bracket` earn anything at scale?** Both sit at noise on
   930 KB, where the match models' 100 MB history is ~1% full. enwik8 dict
   runs are in flight.
3. **How do mechanisms scale?** Points at 50 KB, 930 KB and 100 MB exist or
   are pending; enwik9 would give a fourth across four orders of magnitude.
4. **Can a tokenizer-derived vocabulary beat the shipped list?** Testable in
   ~90 s per candidate against the null build's 4.7485 / 5.9210 / 8.0004
   reference points, with no modelling confound. Constraint in §2.2; cost
   target in §2.3.
5. **What is the exact split of the 6.64 bits?** Needs leave-one-in or Shapley
   (§3.2). Leave-one-in variants are defined but not yet run.
