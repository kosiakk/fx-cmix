# fx2-cmix: a study of the current Hutter Prize holder

> **Status: STUDY OF PRIOR ART — not a proposal, not source of truth.**
> This reads kaitz & Knoll's `fx2-cmix` (Hutter Prize, October 2024) from its
> source and asks what, if anything, transfers to this project. Nothing here is
> measured on our stack. Where a claim about fx2-cmix could not be established
> from the code without building and running it — which the study deliberately
> did not do — it is marked **could not determine**. Claims about *our* side
> point at [[naive-bayes-model]], [[tokenizer-score]], [[spectral-analysis]],
> [[order-and-association]] and the proposal in [[hierarchical-modes]].
>
> Citations are `path:line` into the clone. fx2-cmix is GPL; this document
> describes and cites, and quotes only the few short lines a claim needs.

---



## 0. Orientation, and the headline numbers

fx2-cmix is a context-mixing (PAQ/cmix lineage) compressor specialised to
enwik9. Result table (`README.md:99-119`): executable **S1 = 441 463 bytes**,
archive **S2 = 110 351 665**, total **S = 110 793 128**, previous record
L = 112 578 322, improvement **1.585 %** (the README writes "1,585%").
Decompression: **65 hours**, **9.5 GiB** peak RAM, ~21 GB scratch disk.

The 441 463-byte executable is not all program. `build_and_construct_comp.sh:34-41`
compresses two data files with cmix itself and concatenates them onto the binary:


| payload                                      | raw                      | compressed (from `README.md:173-181`) |
| -------------------------------------------- | ------------------------ | ------------------------------------- |
| `dictionary/english.dic`                     | 411 996 B, 44 515 words  | ≈ **100 088 B**                       |
| `src/readalike_prepr/data/new_article_order` | 1 094 862 B, 172 277 ids | ≈ **201 043 B**                       |


so ~**301 KB of the 441 KB executable is transmitted side information**, and the
actual compiled+UPX'd binary is only ~140 KB. Two consequences worth holding
onto: the article reordering must buy back more than 201 KB (0.18 % of S) before
it is worth anything, and the word dictionary must buy back 100 KB.

**README-vs-code disagreement (finding).** The `README.md:173-181` "expected
output" block prints those two runs as `100088 bytes -> 411996 bytes` and
`201043 bytes -> 1094862 bytes`, but `runner.cpp:467-469` prints
`input_bytes -> output_bytes`, and `RunCompression` (`runner.cpp:206-256`) sets
`input_bytes` to the size of the input file. So the README's pairs are
**reversed** relative to what the code emits, and they are listed in the opposite
order from the build script's invocations. The byte values are almost certainly
right (411 996 is exactly `english.dic`, 1 094 862 exactly the order file); the
presentation is stale. Read them as compressed→original.

---



## 1. Inventory of tricks



### 1.1 Pipeline shape

`runner.cpp:390-438` (`-e`, compress enwik9):

1. `selfextract_comp()` — split the executable, decompress `.dict` and
  `.new_article_order` out of its own tail (`readalike_prepr/self_extract.h`).
2. `split4Comp()` — cut enwik9 at **hardcoded line numbers** into
  `.intro` / `.main` / `.coda` (`readalike_prepr/misc.h:2-8`:
   `COMP_MAIN_END_LINE 13146932`, and separate, differently-valued constants for
   the decompression side).
3. `reorder()` — permute the 172 277 non-redirect articles
  (`readalike_prepr/article_reorder.h:92-164`).
4. `phda9_prepr()` — the wikitext/XML transform (`phda9_preprocess.h:849-861`).
5. `preprocessor::Encode` — text detection + WRT word substitution
  (`preprocess/preprocessor.cpp:220-232`).
6. `Pretrain` on the dictionary text, then arithmetic-code every bit
  (`runner.cpp:249-251`).

Decompression runs the inverse chain and additionally `sort()`
(`article_reorder.h:166-185`) which restores original article order by sorting on
`<id>` — so the *inverse* permutation is never transmitted, only the forward one.

### 1.2 Preprocessing and transforms

Covered in depth in §2. Summary: article reordering; a Wikipedia-XML transform
that strips per-revision header fields into a side stream, delta-codes `<id>`,
re-packs timestamps, moves interlanguage-link tails to a side stream, rewrites a
handful of HTML entities, and swaps run-lengths of `{`/`}`/`[`/`]`; then a
paq8-lineage WRT that lowercases words with case-flag bytes and substitutes
dictionary codes; then a byte-value permutation.

### 1.3 Dictionary and word model

- **Dictionary**: `dictionary/english.dic`, 44 515 lowercase a–z words, one per
line, order-significant (§2.2). Loaded twice: by the *preprocessor*
(`preprocess/dictionary.cpp:37-67`) to build the substitution map, and by the
*model* (`models/fxcmv1.cpp:368-381`, `408-423`) to reverse the substitution
online.
- **Reverse dictionary transform** (new in fx2 per `README.md:25`): the model
keeps a second buffer of *decoded plaintext*. As codeword bytes arrive it
decodes them back to the word (`fxcmv1.cpp:427-435`, `3701-3714`) and pushes
the letters into `cwbuf` (`fxcmv1.cpp:3692-3697`). Every word-level context
downstream therefore sees real English, not opaque codes.
- **Stemmer**: a modified Porter2 from paq8px (`fxcmv1.cpp:2581-3125`), extended
with word-type classes `Article, Conjunction, Adposition, ConjunctiveAdverb`
alongside `Verb/Noun/Adjective/Male/Female/Plural/Prefix/Suffix`
(`fxcmv1.cpp:3627-3643`). Types are packed to 4 bits and shifted into a
`lastWT` history (`fxcmv1.cpp:3673`).
- **Four word streams** (`README.md:30-35`, implemented `fxcmv1.cpp:3681-3688`):
raw `word0`; `worcxt` (sentence, all words, reset at `.`/`;`/newline);
`worcxt1` (paragraph, excluding Conjunction/Article/Male/Female/Number/
ConjunctiveAdverb); `worcxt2` (long stream, additionally excluding Adposition
and AdverbOfManner). Capacity 256 words each (`fxcmv1.cpp:2077-2080`, `vec<…,64*4>`).
**This is a distance-dependent vocabulary**: function words are visible to the
short-range context and invisible to the long-range one. See §6.4.
- **Bracket-scoped word deletion**: words between `(`…`)`, `[`…`|`, `<`…`:`,
`<`…`>`, and `=`…`|` inside templates are *popped off* the word streams
(`fxcmv1.cpp:4200-4207`), so a link's display-text plumbing does not pollute
sentence context.
- **Hand-coded lexical rules**: "a word preceded by `the` is a Noun" is asserted
outright, with the code's own disclaimer — `fxcmv1.cpp:3665` reads
"This is not correct way." — and the Verb word-list match is disabled past a
hardcoded corpus offset with the comment `//77,06% disable`
(`fxcmv1.cpp:3119`).



### 1.4 Context models

Two families feed one mixer stack.

**cmix side** (`predictor.cpp:7-122`): a bracket byte-model
(`models/bracket.cpp`), mod_ppmd (`models/ppmd.cpp:1-3`, adapted by Shelwien
from Shkarin's PPMd), 10 sparse word-context indirect-nonstationary models and 5
sparse word match models (`predictor.cpp:59-94`), 5 hashed order-{0,1,7,11,13}
match models (`predictor.cpp:96-114`), 4 double-indirect models
(`predictor.cpp:116-122`), and an LSTM byte mixer. `README.md:22` records that
fx2 *removed* 7 indirect, 6 match models and 3 mixers relative to fx-cmix to buy
time for a heavier fxcm.

**fxcm side** (`models/fxcmv1.cpp`, ~4.8 kLOC, the bulk of the model): three
ContextMap classes differing only in bytes-per-context — 32 B (`ContextMap1`,
8 slots), 64 B (`ContextMap`, 6 slots) and 128 B (`ContextMap2`, 18 slots) —
sized 32 KiB to 64 GiB-equivalent hash tables at `fxcmv1.cpp:3276-3315`.
`README.md:43` states the rationale (32 B for <256 KiB contexts, 64 B up to
16 MiB, 128 B above). Their contexts are set at `fxcmv1.cpp:4245-4490`, and are
structurally interesting rather than merely order-*n*:

- **Quantised byte streams.** Every byte is mapped through `wrt_2b`/`wrt_3b`/
`wrt_4b`/`wrt_5b` tables to a 2-, 3-, 4- or 5-bit class, and shifted into
`stream2b`, `stream3b`, `stream4b` histories, with *non-repeating* variants
`stream2bR`, `stream3bR` that only shift when the class changes
(`fxcmv1.cpp:4068-4083`, `context-manager.cpp:73-149`). A coarse, long-range,
run-collapsed shape-of-the-text signal.
- **Bracket context** (`fxcmv1.cpp:1852-1916`): a stack of open
`()`/`{}`/`[]`/`<>` with a per-level distance counter; context = (bracket byte,
distance). Also instantiated for quotes and for a "first char of line" stack.
- **Column/table context** (`fxcmv1.cpp:1919-2066`): tracks the last 4 lines,
wiki table state (`{|`, `|-`, `|`, `||`, `|}`), and computes the byte *in the
cell directly above* (`abovecellpos`), used as context at
`fxcmv1.cpp:4339-4352`.
- **Indirect contexts** (`fxcmv1.cpp:4209-4228`): byte→history-of-what-followed
tables, i.e. "what usually comes after the thing that usually comes after this".
- **Sparse match model** with gaps of 1–2 bytes and minimum length 3–6
(`fxcmv1.cpp:1661-1801`), added specifically for escaped UTF-8 (`README.md:45`).
- **Semantic-ish word contexts**: last verb in the paragraph, first word of the
sentence, last non-adjective sentence word paired with the last adjective, etc.
(`fxcmv1.cpp:4272-4281`).

`predictor.cpp:140` prints `num models 461` — 461 predictions enter the mixer.

### 1.5 Mixing and SSE

Three stages.

1. **fxcm's integer mixers** — 12 of them (`fxcmv1.cpp:3244-3255`), each a
  context-selected weight vector over ~515 inputs; sizes 2048 … 0x20000
   contexts. `mxA[10]`/`mxA[11]` combine the other ten
   (`fxcmv1.cpp:4664-4675`). Notable: `mxA[8]` is keyed by the **dictionary
   index of the current word** (`fxcmv1.cpp:4495`). Weight updates are skipped
   when the error is below a running threshold `elim`
   (`fxcmv1.cpp:4688-4692`) — a speed trick (`README.md:19`).
2. **cmix's float mixers** — 23 first-layer mixers over 461 inputs plus one
  second-layer mixer (`predictor.cpp:143-170`), each keyed by a different
   context. Implementation detail that matters for §4: each mixer stores weights
   in a hash map with a **hard cap of 10 000 distinct contexts**; past that,
   everything shares one fallback weight vector (`mixer/mixer.cpp:18-41`).
   `mx19cxt` is set to the fxcm dictionary index (`context-manager.cpp:205`,
   `fxcmv1.cpp:4494`).
3. **APM/SSE** — six APMs inside fxcm chained on the final prediction
  (`fxcmv1.cpp:4730-4754`), blended with two hardcoded weight sets selected by a
   recent-failure bitmask; then cmix's `SSE` (`mixer/sse.cpp:1-3`, Shelwien's
   mod_ppmd SSE) on the output (`predictor.cpp:242`).

The mixer *context* is the real mechanism here: it selects which weight vector
mixes the experts, which makes the mix a **gated, multiplicative** combination
even though each mixer is linear. That is the cheap version of the conjunction
layer [[hierarchical-modes]] wants; see §5.

### 1.6 The coder

A plain binary arithmetic coder, carryless, 32-bit range, 16-bit probability
(`coder/encoder.cpp:14-31`, `coder/decoder.cpp`). One bit at a time, MSB-first
over bytes (`runner.cpp:143-151`). Nothing unusual.

### 1.7 Parameter fitting and offline training

This is where fx2-cmix is furthest from our conventions.

- **Pretraining**: before compressing, the predictor is run over the whole
dictionary text as if compressing it (`preprocess/preprocessor.cpp:18-50`,
invoked at `runner.cpp:250`). Free because the decoder has the dictionary.
- **Hardcoded corpus offsets**: model behaviour switches at literal byte
positions in the *preprocessed* stream — `x.blpos<448131719`
(`fxcmv1.cpp:3837`, `3848`), `x.blpos>463139793` (`fxcmv1.cpp:3884`),
`x.blpos<451531986` (`fxcmv1.cpp:3119`). Also `NUM_OF_ARTICLES 243425`
(`article_reorder.h:12`) and the six line numbers in `misc.h:2-8`.
- **Hand-tuned constant arrays**: `c_r`, `c_s`, `c_s3`, `c_s4` — 27 entries each,
one per ContextMap, labelled "contextmap run mul" / "contextmap pr mul"
(`fxcmv1.cpp:3134-3137`); `e_l[8]`, the per-bit-position failure thresholds
(`fxcmv1.cpp:3139`); six 7-parameter state-table generators
(`fxcmv1.cpp:4787-4792`); a 256-entry hardcoded nonstationary state table
(`states/nonstationary.cpp:3`).
- **Build-time constants**: `SEED="923"`, `UPDATE_LIMIT="3000"`
(`build_and_construct_comp.sh:6-7`), plus profile-guided optimisation with a
Wikipedia-shaped profile input (`makefile` `prof_gen`/`prof_use`,
`prof_input/input`).
- **The article order itself** is fitted offline with a commercial embedding API
(§2.3).

None of this is reproducible from a specification. It is reproducible from *this
binary*, which for the Hutter Prize is the only requirement.

---



## 2. Wiki-specific tricks (the priority section)



### 2.1 What the preprocessor rewrites, and whether it inverts

Everything below is in `src/readalike_prepr/phda9_preprocess.h`; `encode_txt_wit`
(`:668-821`) is the forward pass, `decode_txt_wit` (`:523-666`) the inverse.
The name and structure descend from Rhatushnyak's phda9; `README.md:65` claims
the fx2 novelty is that it is now **single-pass** (disk 18 GB → 7 GB, 7 min → 3 min).

**Three output streams, concatenated.** The forward pass writes the main text to
`out`, per-revision header fields to a temp file `out3`, and interlanguage-link
tails to a temp file `out1`; at the end it appends `[header size]\n[lang size]\n [header stream][lang stream]` to the main file and back-patches a 21-byte
tail-length field at offset 0 (`:781-820`). So the compressed-side layout is
main-text ‖ headers ‖ language-links. **All three are exactly recoverable**: the
decoder seeks to the tail, reads the two lengths, and replays.


| rewrite                                                                                                                                            | where                                           | invertible?                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `<id>` per revision → delta from previous id, decimal                                                                                              | `:698-707` fwd, `:584-588` inv                  | yes, exactly                                                                                                     |
| `<timestamp>` → `yy`, `month*31+day-32`, `h*3600+m*60+s`                                                                                           | `:711-721` fwd, `:590-597` inv                  | yes; the `d/31+1, d%31+1` inverse is exact for the 1-31 day range                                                |
| all other page/revision header tags (`<ns>`, `<contributor>`, `<username>`, …) → tag-name-only lines in the header stream, indentation regenerated | `:723-747` fwd, `:555-629` inv                  | yes; the decoder rebuilds `<x>…</x>` and the 4/6/8-space indent from tag names                                   |
| `&` → `&`, `"` → `"`, `<` → `<`, `>` → `>`                                                                                                         | `hent`/`hent2` `:214-276`                       | yes, with an escape: a literal `&` that would collide is marked with byte `3` (`:234`)                           |
| `` → `&!`, `&ndash;` → `&*`, `&mdash;` → `&^`, `&deg;` → U+00B0, `&times;` → U+00D7                                                                | `hent2` `:246-276`, `hent3` `:186-212`          | yes; note `&reg;`, `&euro;`, `&sup2;`, `&sup3;`, `&isin;`, `&rarr;`, `&minus;` are present but **commented out** |
| `&#NNN;` with NNN > 255 → escape byte `5` + raw UTF-8                                                                                              | `hent5` `:279-301`, inverse `hent6` `:164-184`  | yes                                                                                                              |
| inside `<text>` only: the `&` before a bare `"`/`<`/`>` is deleted                                                                                 | `removeamp` `:343-356`, `restoreamp` `:357-367` | yes, positionally (only after the `<text …>` opening tag)                                                        |
| run-length swap of `{`, `}`, `[`, `]`: runs of 1↔2                                                                                                 | `hent9` `:303-334`                              | yes — it is an involution, applied on both sides                                                                 |


That last one is the single biggest textual win and deserves spelling out.
`[[Article]]` becomes `[Article]`, `{{Template}}` becomes `{Template}`, and the
comparatively rare single `[` becomes `[[`. Two bytes saved per wiki link, on a
corpus that is mostly wiki links. The model is written against the transformed
form — `fxcmv1.cpp:1962` checks for the three-byte sequence `{{|` when detecting a
table start, which is what `{|` becomes after the swap.

**Two findings on** `hent9`**.**

1. `PROCESS(0x27, …)` — the same run-swap for `'` — is present and **commented
  out**, with the comment `// breaks wordmodel` (`:320`, `:326-327`). So
   collapsing `''`/`'''` emphasis was tried and rejected: it saves bytes but
   destroys the word model's ability to segment. Emphasis is instead handled as
   *context*: a quote-bracket stack (`fxcmv1.cpp:3318`) and a paragraph-start
   heuristic keyed on `''`-delimited leading text (`fxcmv1.cpp:4178-4189`).
2. The `PROCESS('&', in, out, 1)` at `:325` writes into `out`, and the trailing
  copy loop at `:328-331` then copies `in` over `out` — so as written, the `&`
   run-swap result **appears to be discarded**. It is applied identically on both
   sides so the round trip is unaffected; I read this as dead code, but since I
   did not build or run the program, treat "the `&` swap is a no-op" as **high
   confidence, not verified by execution**.

**Exact invertibility overall: yes on enwik9, by construction plus four
hardcoded patches.** `:437-443` contains literal exception strings —
`"r:Wikipédia:Aide]]"`, `"de:Boogie Down Produ"`, `"da:Wikipedia:Hvordan"`,
`"sv:Indiska musikinstrument"` — that suppress the language-tail rule on four
specific enwik9 lines that would otherwise be misclassified. A further block of
~40 namespace prefixes (`Kategoria:`, `Datei:`, `wikisource:`, `doi:`, …) sits
commented out at `:401-436`, evidence of a long tuning history. On arbitrary
wikitext the transform is **not** proven invertible; on enwik9 it is, because it
was tuned until it was.

**Numbers.** There is no number transform in the wikitext body. Numbers are
handled purely as *context* in the model — `number0`/`number1`/`numlen0/1` parse
`123`, `12.34`, `1,234` shapes (`fxcmv1.cpp:3857-3871`) and feed context maps
(`fxcmv1.cpp:4255`, `4322`, `4452`). Only the XML timestamp is re-encoded.

**Whitespace.** Not rewritten in the body. Header-line indentation is dropped and
regenerated (`:559-563`, `:619-627`). Line-leading spaces are *modelled*: the
first character of the line is a context, and a run of leading spaces suppresses
the order-3..5 context maps entirely (`fxcmv1.cpp:3779-3784`).

**Case.** Not in phda9 — case markers belong to the WRT layer, §2.2.

### 2.2 `dictionary/english.dic`: how it is built, and how codes are assigned

**How it is used** (`preprocess/dictionary.cpp:37-67`). Words are read in file
order; only `a`–`z` runs count as words; the *line number* alone determines the
code:


| lines         | code length | first emitted byte        | second                    | third                |
| ------------- | ----------- | ------------------------- | ------------------------- | -------------------- |
| 0 – 79        | 1 byte      | `0x80 + i`                | —                         | —                    |
| 80 – 3919     | 2 bytes     | `0xD0 + (i-80)/80`        | `0x80 + (i-80)%80`        | —                    |
| 3920 – 44 879 | 3 bytes     | `0xF0 + ((i-3920)/80)/32` | `0xD0 + ((i-3920)/80)%32` | `0x80 + (i-3920)%80` |


(boundaries `kBoundary1=80, kBoundary2=3920, kBoundary3=44880` at
`dictionary.cpp:43-44`; byte order from `EncodeBytes` `:23-33`, least-significant
first).

Read that table again as a tree. The dictionary order defines a **3-level
hierarchical code over the vocabulary**: 16 super-blocks of 2560 → 32 blocks of
80 → 80 words. The first byte names a group of 2560 dictionary lines; the second
narrows to 80; the third picks the word. This is exactly class-based
hierarchical softmax with a hand-built clustering — and the model exploits it as
such (§3, §4).

Case is carried by three marker bytes emitted *before* the word
(`dictionary.cpp:10-13`, `123-138`): `0x40` = capitalized, `0x07` = all-upper,
`0x06` = end-of-upper-run, `0x0C` = escape for a literal marker byte or a byte
≥ 0x80. Words not in the dictionary get a **longest-suffix then longest-prefix**
fallback (`EncodeSubstring`, `:140-169`): for a word > 7 chars, try the longest
suffix ≥ 7 chars that is in the dictionary, emitting the unmatched head
literally; else the longest prefix. That is a crude, deterministic, one-level BPE.

A final **byte-value permutation** is applied to the whole WRT output
(`preprocess/preprocessor.cpp:136-139`, inverse `dictionary.cpp:180-187`,
model-side copy `fxcmv1.cpp:2204-2210`): `{`…`~` → `P`…, `:;<=>?` and `JKLMNO`
swapped, `X`↔```. Its effect is to move markup punctuation into the
uppercase-letter range that WRT has vacated, keeping the used-byte alphabet small
and contiguous — `runner.cpp:111-124` extracts exactly the set of used byte values
and passes it as `vocab` to the LSTM, whose input/output width *is* that count
(`predictor.cpp:127-132`). Note what this is: a **relabelling of the leaves of the
8-bit binary tree the coder walks**, chosen by hand. Hold that thought for §4.

**How the dictionary was built: could not determine from this repository.** There
is no build script, no frequency list, no provenance note. What *is* determinable
is its structure, by inspection:

- lines 1–80 (1-byte codes) are pure frequency/utility:
`will would can may it there he they right px jpg th org com http united is was has had are were …` — note `px`, `jpg`, `org`, `com`, `http`, `category`,
`image`, `states`, i.e. wiki-specific tokens promoted into the 1-byte tier.
- lines ~1000–1040 are a modal/comparative verb cluster
(`seek want wish seem … opposed compared unable able attributed referred`).
- lines ~3000–3040 are period/nationality adjectives
(`arab european soviet imperial royal national … medieval local traditional`).
- lines ~4000–4040 are a junk/URL-fragment block
(`consol constitucion contrass couldn cript crtc … dhcp dhtml`) — parked right
after the 2-byte boundary at 3920.
- lines ~10 000–10 040 are verbs (`circumvent … constrain`).
- lines ~20 000–20 040 are chemistry (`butane butanol … chromosomes`).
- lines ~40 000–40 040 are rock musicians (`halen … vangelis`).

So the dictionary is **already frequency-tiered at the top and topically
clustered in the tail**. This is the paq8hp/phda lineage dictionary, curated over
roughly two decades. Its 80-word blocks and its 2560-word super-blocks are, by
construction, the classes of the hierarchical code above.

### 2.3 `src/article_order/`: reordering, transmitted

**The pipeline** (`README.md:56-62`, notebooks in `src/article_order/`):

1. `embeddings.ipynb` — for each non-redirect article, take title + first 4000
  chars of `<text>` with multi-line `{{…}}` templates stripped, and embed with
   **Voyage AI's** `voyage-large-2-instruct`, 1024 dimensions, over a paid API.
2. `tsne.ipynb` — t-SNE to **one** dimension, `max_iter=80000`.
3. sort by that scalar (a shell `sort`, `README.md:59`).
4. `kmeans.ipynb` — 1-D k-means with `clusters = floor(n/80)`, then **within each
  cluster sort by original enwik9 article index**.
5. `tac` to reverse.
6. `manual-sort.ipynb` — push Image pages, disambiguation pages, `{{hndis}}`,
  `{{geodis}}` and US-census-boilerplate articles to the end.

**Transmitted, not derived.** `build_and_construct_comp.sh:36` compresses
`new_article_order` into the executable. The decompressor reads it back out
(`self_extract.h`), applies it in reverse, and finally restores true order by
sorting on `<id>` (`article_reorder.h:166-185`). So the *forward* permutation
costs bits; the inverse is free.

**What it costs.** 172 277 ids, ≈ **201 043 bytes** compressed = **9.34 bits per
article**. A uniformly random permutation of 172 277 items needs
log2(172 277) ≈ 17.4 bits each (≈ 375 KB). The order file compresses to 54 % of
that because step 4 sorts *within* cluster by original index, making the file a
sequence of ascending runs. That is a deliberate, and quite elegant, choice: it
buys clustering while giving back most of the permutation's entropy.
`article_remap.cpp:1-3` states its own purpose in the same spirit — renumber to
skip redirects "we can improve compression of the article order file".

**Why reordering pays at all**: the models are *online-adaptive*. Putting
semantically similar articles adjacent keeps the match models, the run maps and
the mixer weights in a locally stationary regime. This is a property of adaptive
compressors and, importantly, **not** of a static counted model — see §6.7.

**How much it buys: could not determine.** The repo contains no ablation.
`README.md:70-73` links three external Google Docs with "improvement graphs" and a
change timeline; those were not fetched. The only hard bound available from the
repo is the floor: it must beat 201 043 bytes.

### 2.4 Interlanguage links — the live question

**Yes, they are special-cased, and the mechanism is segregation into a separate
stream.** `henttail` (`phda9_preprocess.h:369-474`) is the forward rule; here is
its detection logic, described precisely:

- A line is a candidate if it starts with `[[` (`:389`) — remember `hent9` has
*not* yet run on it, so this is still the raw double bracket.
- Scan from index 2 for the first character outside `a`–`z` (`:391-393`); the
candidate holds if that character is `:` and neither `in[2]` nor `in[3]` is `:`
(`:394`). So the shape matched is `[[` + lowercase-run + `:` — precisely
ISO-639 interlanguage prefixes.
- **Excluded** (`:395-400`): `http:`, `user:`, `media:`, `Image:`/`image:`
(tested as `"mage:"` at `ps[3]`), `Category:`/`category:` (as `"ategory:"`).
These stay inline.
- Excluded if fewer than 4 lines have passed since `<text` (`lnu-b1<4`, `:444`),
with the comment `// skip if not lang at end` — i.e. the block must be at the
end of a body of real length.
- Excluded for the four hardcoded enwik9 lines quoted in §2.1.
- Excluded inside `<comment>` (`co` flag, `:378-386`).

Once a line matches, `f=1` and **every line from there to** `</text>` **inclusive** is
written to the language stream and erased from the main stream (`:445-473`;
`out[0]=0` blanks the main-stream line, `wfputs(in,o)` appends to the side file).

The inverse, `henttail1` (`:476-518`), is worth admiring. It reinserts the tail
when it sees `</revision>` while its `<text>`-open flag `c` is still 1 and the
body was ≥ 4 lines (`:488`). The flag is still 1 precisely because the `</text>`
line was among the diverted lines. **The presence or absence of** `</text>` **in the
main stream is itself the signal** — no length field, no marker byte, no side
channel. It then copies lines from the language stream until it consumes the one
ending `</text>` (`:509`).

Now the three sub-questions, answered from the code:

- **Does it exploit the sorted order of language codes?** *No.* Nothing sorts,
delta-codes or otherwise models the `fr`/`de`/`ja` prefix sequence. It is left
entirely to the general context models, which see the concatenated language
blocks of *all* articles as one contiguous region and will pick up the
regularity through match models and order-*n* contexts.
- **Does it exploit similarity between the English title and the translated
title?** *No.* I grepped for title handling across `models/fxcmv1.cpp`,
`readalike_prepr/*` and `preprocess/*`: the only uses of `<title>` are
`phda9_preprocess.h:633` (detecting the end of a title line, to start header
capture) and `article_reorder.h:59-60`, `:148`, which are inside
`#ifdef DUMPARTICLE` — a debug dump. The title is **never** available to the
model as a reference string for the translated titles. Given that
`[[fr:Alsace]]` under `<title>Alsace</title>` is a near-copy, this looks like
real headroom — but the tail segregation partially captures it anyway, because
the article's own body text (containing the title) is a few hundred KB away in
the reordered stream and the match models have a 60 M-byte history
(`context-manager.cpp:58`).
- **Does it exploit the near-mechanical slug transformation?** *No.* No
transliteration, no diacritic folding, no space↔underscore rule anywhere in the
transform.

**The only model-side acknowledgement of language links is a single comment.**
`fxcmv1.cpp:4374` sets a context on the sentence's first word and remarks
"all category/language/image links (better as standalone)" — i.e. the author knows
these three link classes are lumped together and believes separating them would
help, and did not do it. And `fxcmv1.cpp:4139` special-cases `[category:` and
`[wikipedia:` by dropping the prefix word from the sentence word stream.

**Summary for our purposes**: fx2-cmix's interlanguage trick is *purely
positional* — move the block, make the boundary self-signalling, let generic
models exploit the resulting density. The *content* redundancy (title↔translation)
is untouched. That is both an endorsement of the cheap move and an explicit
statement of where headroom remains.

### 2.5 Namespace prefixes, tables, emphasis

- `Category:` **/** `Image:` **/** `Template:` — not extracted, not rewritten.
`Category:` and `Image:` are explicitly *excluded* from the language-tail rule
(`phda9_preprocess.h:399-400`). At model level: the `[category:` / `[wikipedia:`
prefix word is popped from the sentence stream (`fxcmv1.cpp:4139`); `[image:`
is kept as a first-char context (`fxcmv1.cpp:4132-4137`) because image links
carry captions that *are* prose; a `[word://` sequence retro-classifies the
context from "namespace link" to "http link" (`fxcmv1.cpp:4143`). `Template:`
gets no name-level handling; templates are handled structurally via `{`.
- **Table markup** — no transform, substantial modelling. `ColumnContext`
(`fxcmv1.cpp:1919-2066`) implements `{|`, `|-`, `|`, `||`, `|}` (the code lists
the full wiki table grammar in a comment at `:1986-1996` and states at `:1996`
that only those five are implemented), tracks up to 4 rows × 32 cell positions,
and exposes the byte in the cell above as context (`:4350-4352`). A second mode,
`WIKIHEADER`, does the same for lines starting with `>` (which is what `<`/`>`
become after the byte permutation) — the XML header block, treated as a table.
- `''` **/** `'''` **emphasis** — no transform (the run-swap was tried and reverted,
§2.1). Modelled as a quote-bracket stack plus several heuristics that treat
`''…''` at the head of a line as the start of a real paragraph
(`fxcmv1.cpp:4178-4189`), and a set of rules that *cancel* the quote context
when `'` is a genuine apostrophe — `x'x`, `]'x`, `y'x` with y a digit, etc.
(`fxcmv1.cpp:3816-3822`, `3872-3879`). Nine lines of case analysis for one
ambiguous character.
- `<math>`**,** `<pre>`**,** `<nowiki>`**,** `<text>` — detected on the *decoded* text
stream (`fxcmv1.cpp:3946-3963`) and used to disable word-level contexts inside
them (`README.md:46`); dozens of `if (isMath) cm.sets();` sites.

---



## 3. The bit-at-a-time question

The hypothesis under test: *"first bit means participation in the highest-energy
mode; following bits are other modes, but maybe conditioned on the first one, not
orthogonal."*

### 3.1 First, a correction about what is being bit-decomposed

fx2-cmix codes **bytes**, not tokens. `runner.cpp:143-151` emits 8 bits per byte,
MSB first, and `bit_context_` — the partially-decoded byte, in the range 1…255 —
is a component of essentially every context (`context-manager.cpp:170-220`,
`long_bit_context_`). So the binary tree the coder walks is depth 8 over a
256-leaf alphabet. It is not a tree over the 44 515-word vocabulary.

The word vocabulary *is* nonetheless hierarchically coded, but by a different
mechanism: the WRT code of §2.2, whose three bytes name super-block → block →
word. Composing the two, a dictionary word is coded as **up to 24 binary
decisions arranged in three groups of eight**, where the group boundaries are
semantically meaningful and the within-group boundaries are not.

This distinction matters, because the model *knows* about the outer hierarchy and
is indifferent to the inner one. `fxcmv1.cpp:3824-3832` decodes the *partial*
codeword after each byte and, when the partial decode resolves, stores it in
`deccode`; `fxcmv1.cpp:4494-4495` feeds `deccode` to two mixers. So after byte 1
of a 3-byte codeword the mixer is conditioned on "which super-block of 2560
words", after byte 2 on "which block of 80", after byte 3 on the exact word. That
is a textbook coarse-to-fine refinement over the vocabulary, and it is the part of
fx2-cmix that the hypothesis is actually about.

### 3.2 Where the analogy genuinely holds

1. **Both are sequential refinements of a distribution over the vocabulary.** A
  prefix code narrows the candidate set; a truncated mode expansion narrows the
   plausible next-token set. In both, an early, coarse, cheap decision precedes
   later fine ones.
2. **Early decisions are cheap and confident, and that is by design in both.**
  fx2-cmix puts the 80 most useful words in a 1-byte tier and the semantic block
   id in the first byte of the rest, so the high-information decision is made
   where the context signal is strongest. Our rank budget does the same thing in
   spirit — spend rank where the lift is.
3. **Both are conditional, in the sense that the later refinement's meaning
  depends on the earlier one.** "Word 37 of block 12" is not "word 37 of block
   4"; and in [[hierarchical-modes]] §2.4 a conjunction correction only means
   something in the presence of its base modes.



### 3.3 Where it breaks — four distinct failures

**(a) A bit-decomposition is a prefix code over a *fixed, context-independent*
numbering; modes are a learned, data-determined basis.** The tree in fx2-cmix is
identical for every context in the corpus; only the *probabilities* on its edges
are contextual. An SVD mode is a direction chosen by the data. Calling the first
bit "the highest-energy mode" mistakes a labelling convention for a decomposition.
The only reason fx2-cmix's first byte carries semantic meaning is that a human
sorted `english.dic` so that it does.

**(b) Energy ordering is not what a prefix code gives you — and it is not what we
should want anyway.** SVD modes are ordered by singular value, i.e. by variance
explained. The first bit of a code is whichever partition of the alphabet the
numbering induces. And our own spec has already measured that even *our* ordering
is not an importance ordering: [[naive-bayes-model#Factorization]] records that
"explained mass is non-monotone in index (factor 2 exceeds factor 1 by a factor of
two), so singular-value order is not predictive-importance order". So the strong
form of the hypothesis — first bit ≈ top mode because both are "most important
first" — is false on both sides of the analogy simultaneously.

**(c) Orthogonality is exactly inverted.** SVD modes are orthogonal by
construction. A prefix code's branches are *nested*: bit 2 is defined only
conditionally on bit 1, and the two are maximally non-orthogonal in the sense that
one is a refinement of the other's partition. The user's instinct that the bits
are "conditioned on the first one, not orthogonal" is **right**, and it is
precisely the reason the analogy to modes fails rather than a way in which it
holds. There is a name for the object: this is the **chain rule**, and
p(w) = ∏ p(bit_i | prefix, context) is *exact and lossless* at any depth. Mode
truncation is lossy by construction. They are not two versions of one thing.

**(d) The composition algebra is different, and this is the most consequential
difference.** In our model, modes compose **additively in log-lift**, over the
*same* symbol, then one global softmax:
s(w) = log π(w) + Σ_d λ_d ⟨u_w, v_c^(d)⟩ ([[naive-bayes-model#Inference]]).
That is a product of experts and it is why we pay for a partition function Z
([[naive-bayes-model#The free normaliser]]). A hierarchical code composes
**multiplicatively in probability**, over *disjoint refinements of the event
space*, and needs **no global normaliser at all** — each node's conditional is
normalised over two (or 256) children. Sum-then-normalise-once versus
product-of-locally-normalised-conditionals is not a change of notation.

This is worth stating positively: **a hierarchical code over the vocabulary is the
standard escape from the free-normaliser cost.** That is the one concrete thing
this analogy is good for, and it is an argument for building the tree, not an
argument that we already have one.

### 3.4 Is prefix conditioning the same as the bilinear conjunction layer?

**No, and conflating them would be a real error.** [[hierarchical-modes]] proposes
a product a_m(t)·a_{m'}(t) of two *input* activations — an interaction in the
feature space, on the context side. Prefix conditioning restricts the *output*
set — a decision tree over labels, on the prediction side. One changes what the
model can represent about the context; the other changes how the answer is
enumerated. A model can have either, both or neither.

There is exactly one place where they touch, and it is worth taking seriously.
If a hierarchical output code is implemented as *a different linear predictor per
node* — which is how fx2-cmix's `mxA[8]` works, one weight vector per dictionary
index (`fxcmv1.cpp:3252`, `4495`) — then the effective model is
(feature) × (node indicator), which is a product of an input activation with a
one-hot output-side gate. That *is* a conjunction, of a restricted, hard-gated
kind. So a hierarchical softmax over a mode-clustered vocabulary is a **cheap,
structured special case** of the bilinear layer, not an alternative to it, and not
the general case [[hierarchical-modes]] is after. It fails the interpretability
bet in §4.4 of that document (the gate is an index, not a nameable mode) while
passing its efficiency test.

Two further mismatches to note against the proposal:

- **Signs.** Our modes are two-sided — loadings carry attract/repel sign and
activations range over ± ([[spectral-analysis]] §2, "Sign, recovered";
[[hierarchical-modes]] §1.1). A bit is a partition, not a signed quantity. A
mode's "participation" is graded and signed; a bit is neither.
- **Thresholding.** Turning "participates in mode 1" into a bit requires a
threshold on a graded activation, which is failure point 5 of
[[hierarchical-modes]] verbatim: "a binary 1[a>τ] co-activation loses graded
information and is τ-sensitive". The bit analogy, taken literally as a
construction rather than an intuition, walks straight into a hazard the proposal
has already flagged.



### 3.5 Verdict: hierarchical softmax over a semantically clustered vocabulary is the right bridge concept

Yes — say it plainly. The correct name for what the user is reaching toward is
**class-based / hierarchical softmax with a semantically-derived class
assignment** (Goodman; Morin & Bengio; Mnih & Hinton — the last already cited in
[[prior-art]] for a different reason). fx2-cmix contains a working instance of it:
a 16×32×80 tree over 44 515 words whose classes are hand-curated semantic groups,
with the partially-resolved class fed to the mixer as it resolves
(`fxcmv1.cpp:3824-3832`).

Our contribution, if we wanted one, is obvious and is *not* "bits are modes": it
is that **the clustering can be derived from the modes instead of by hand**. Take
the mode loadings as a vocabulary embedding, cluster it, use the clusters as the
tree's classes. That gives an interpretable, spec-able, corpus-derived hierarchy
which (i) kills the Z cost and (ii) is measurable against a flat softmax on
held-out bpc. It should be filed as its own proposal, not smuggled into
[[hierarchical-modes]], because it is a decomposition of the *output* space and
that document is about the *feature* space.

---



## 4. Would reordering their vocabulary alone give ~1 %?

**Short answer: no, and the code says why. Estimated headroom is one to two orders
of magnitude short of 1 %.** The reasoning, in order of force.

### 4.1 Where the ordering actually enters

Three places, and only three.

1. **Code length.** Lines 0–79 cost 1 byte, 80–3919 cost 2, 3920+ cost 3
  (`dictionary.cpp:43-60`). This is by far the largest lever, and it is a pure
   *frequency* question, not a semantic one.
2. **The prefix-code classes.** The first byte of a 2-byte code names a block of
  80 lines; of a 3-byte code, a super-block of 2560 then a block of 80 (§2.2).
   Clustering related words into the same block makes the first byte predictable
   from topical context — this is the real "semantic ordering helps" channel.
3. **Mixer contexts keyed on the index.** `mxA[8].cxt = deccode`
  (`fxcmv1.cpp:4495`) and `mx19cxt = wrtcxt = deccode`
   (`context-manager.cpp:205`, `fxcmv1.cpp:4494`).



### 4.2 Channel 3 is nearly inert, for a specific implementation reason

`mxA[8]` is a **direct-indexed** array of 0x20000 = 131 072 context slots
(`fxcmv1.cpp:3252`); `deccode` is either the exact word index (0…44 515) or
`0x10000 + stream2b` for non-words (`fxcmv1.cpp:3837`, `3851`). Direct indexing
means **adjacent indices share nothing** — word 12 000 and word 12 001 get
entirely separate 55-weight vectors. Moving two related words next to each other
does not pool their statistics at all.

Worse on the cmix side: `mixer/mixer.cpp:18-41` caps each float mixer at
**10 000 distinct contexts**, after which every new context falls back to one
shared `context_base_`. With `mx19cxt` keyed on a 44 515-value index, roughly
three quarters of the dictionary shares a single weight vector, allocated
first-come-first-served in stream order.

The only way index adjacency helps these mixers is through the *partial* decode
(`fxcmv1.cpp:3830-3831`, "Change only when found"), which sets `deccode` to the
block-level index while the codeword is still arriving. That is channel 2 again,
not an independent effect.

### 4.3 The authors have already tuned all three channels, hard

- **Channel 1** is visibly frequency-sorted, and wiki-specifically so: the 1-byte
tier contains `px`, `jpg`, `org`, `com`, `http`, `category`, `image`, `states`
— corpus artifacts promoted past ordinary English words. Somebody counted.
- **Channel 2** is visibly semantically clustered — verbs at ~10 000, chemistry at
~20 000, musicians at ~40 000, a junk/URL block parked immediately after the
2-byte/3-byte boundary at 3920 (§2.2). That last placement is a deliberate
choice to keep low-value strings out of the 2-byte tier.
- **The byte alphabet itself has been reordered** — `charSwap`
(`fxcmv1.cpp:2204-2210`, `preprocessor.cpp:136-139`) is literally "relabel the
leaves of the coder's binary tree so the bit-prefix predictions get easier",
with a comment at `preprocessor.cpp:132` explaining that the block marker was
chosen "to keeb vocab size small". If reordering-the-alphabet were an untapped
seam, this is where it would show, and it has been mined.
- The repo also carries every other sign of exhaustive tuning: hand-fitted
27-entry constant arrays, six generated state tables, hardcoded corpus offsets
with a `//77,06% disable` annotation, PGO and a fixed RNG seed (§1.7).

This is a lineage — paq8hp → phda9 → fx-cmix → fx2-cmix — in which dictionary
ordering has been a first-class tuning knob for roughly twenty years, on this
exact corpus, by people whose entire objective function is enwik9 bits.

### 4.4 The arithmetic

1 % of S = 110 793 128 is **1 107 931 bytes**. The *entire* fx2-cmix improvement
over the previous record was 1 785 194 bytes (1.585 %), and `README.md:16-53`
attributes it to a large basket: NLP/stemmer word types, the reverse dictionary
transform, the single-pass transform, the new article order, mixer-context
changes, split ContextMaps, the sparse match model, and more. Asking one knob —
and a knob already at a local optimum — to deliver 62 % of that basket is not
credible.

A sanity bound on channel 1: to gain 1 MB by tier promotion alone you would need
~1 M word-occurrences to drop a byte, i.e. ~1 M occurrences currently in the
3-byte tier that belong in the 2-byte tier. The 2-byte tier holds 3840 words on a
~1 GB corpus; the boundary is deep in the Zipf tail already. Channel 2's ceiling
is likewise bounded by the total entropy of first bytes of multi-byte codewords,
which is a small fraction of the stream.

### 4.5 What *would* be worth trying, honestly stated

- **Replacing the dictionary contents**, not merely its order — e.g. a vocabulary
selected by our merge criterion ([[tokenizer-score]]) rather than by hand. This
is a genuinely different lever and it is not obviously exhausted. But it
interacts with `EncodeSubstring`'s prefix/suffix fallback, with the stemmer, and
with the transmitted-dictionary cost (~100 KB), and it is a rewrite rather than
a reorder.
- **Interlanguage-link content modelling** (§2.4) — the one place the code
demonstrably leaves value on the table, and where `fxcmv1.cpp:4374`'s own
comment says so.
- **A better article order** from our spectral embedding rather than
t-SNE-of-Voyage. Plausible; bounded below by the 201 KB order-file cost; and
note the authors already spent a paid embedding API and six pipeline stages on
it, so it is not virgin ground either.

**A well-argued no is the answer here.** Reordering `english.dic` alone will not
produce ~1 %. The most likely outcome of such an experiment is a result in the
0.01–0.1 % range, of either sign.

---



## 5. Similarities and differences, honestly



### 5.1 Where the two projects agree

- **Exact bits, end to end.** fx2-cmix counts its own decompressor in the score
(S = S1 + S2). We count transmission of the vocabulary and the tables
([[naive-bayes-model#Transmission]]) and evaluate on exact enwik bytes. Same
discipline; neither project permits a free model.
- **Preprocess the wikitext.** Both treat markup as a corpus artifact to be
handled analytically rather than learned. Compare `hent9`'s bracket run-swap
and the entity table to `seed_markup!` (`src/Bytes.jl:115`) and
[[tokenizer-score#Admissibility]]'s "seed what is analytically certain, score
what is statistical". Our version discovered 4 entities and 57 complete tags
from the corpus's own grammar; theirs is a hand-written table with commented-out
history. Ours is the better-founded construction; theirs has 20 years of
measurement behind its choices.
- **Context at multiple distances.** Our distance-*d* directed tables
([[order-and-association]]) and their order-*n* context maps plus sparse/skip
contexts are the same underlying claim: prediction lives at several ranges and
the ranges must be combined.
- **Case and boundary normalisation as separate marker bytes.** `kCapitalized`
/ `kUppercase` / `kEndUpper` (`dictionary.cpp:10-13`) are the same idea as
`TITLE_MARKER` and `KEEP_SPACE` in `src/NormalizeV3.jl:38-40`, arrived at
independently, for the same stated reason: one spelling, per-instance
modifiers.



### 5.2 Where they genuinely diverge


|                  | fx2-cmix                                                       | this project                                                 |
| ---------------- | -------------------------------------------------------------- | ------------------------------------------------------------ |
| fitting          | **online**, adaptive, single pass, no train/test split         | **offline**, static counted tables + low-rank fit            |
| combination      | 461 experts, context-gated learned mixing, 3 stages            | fixed additive log-lift, λ_d per distance                    |
| unit             | **bit** over bytes                                             | **token**                                                    |
| interpretability | none claimed; mixer weights are opaque                         | the entire point ([[spectral-analysis]] printing convention) |
| neural           | 1-layer LSTM, 200 cells, horizon 128 (`predictor.cpp:131-132`) | explicitly none                                              |
| provenance       | binary is the spec; hardcoded offsets, PGO, fitted tables      | `specs/` is source of truth; code reproducible from specs    |
| calibration      | six APMs + SSE on the final probability                        | none                                                         |




### 5.3 What fx2-cmix does better — named, not hedged

1. **Adaptivity removes the stationarity assumption entirely.** No held-out split,
  no drift problem, no rank-selection question. Our whole apparatus for choosing
   rank and validating against a resplit null ([[order-and-association#Degeneracy]])
   exists because we fit once.
2. **Context-gated mixing is a conjunction layer that actually ships.** The mixer
  context selects the weight vector, so the combination of experts is
   multiplicatively gated on the context. That is the capability
   [[hierarchical-modes]] argues the additive stack lacks, obtained for the price
   of a hash lookup, with no combinatorial explosion because the gate is a hashed
   context rather than an enumerated pair.
3. **Final-stage calibration (APM/SSE).** Mapping (prediction, small context) →
  corrected prediction is cheap and routinely worth low single-digit percentages
   in this literature. We have no analogue at all.
4. **Structural side-channels that a distance-*d* table cannot express**: bracket
  nesting depth *and* distance-within-bracket, the byte in the table cell
   directly above, the first character of the line as a stack. These are
   deterministic functions of the text that carry real signal and are invisible to
   any pure co-occurrence statistic.
5. **The self-signalling stream split** (§2.4) — using the absence of `</text>`
  in the main stream as the reinsertion flag. Zero-cost framing. Elegant.
6. **It is finished.** A 65-hour, 9.5 GiB, exactly-reversible, self-extracting
  artefact that beat a standing record. That is a different and harder kind of
   done than any of ours.



### 5.4 What we do better

Interpretability as a first-class outcome; a stated null and a principled
estimator rather than tuned constants; a merge criterion derived rather than
stipulated ([[tokenizer-score#The criterion]]); specs that a second
implementation could be built from. Also: our vocabulary is *derived from the
corpus by a specified procedure*, where theirs is an external artefact of unknown
provenance (§2.2) that must be shipped in the archive.

---



## 6. What we should steal, ranked by expected value ÷ effort

Ordering is by ratio, not by size of prize. Each entry names the file it would
touch and how it would be measured. Convention flags are explicit: `specs/` **is
source of truth and code must be reproducible from it**, so anything offline-fitted
or externally sourced is a real departure that must be spec'd, not smuggled in.

### 6.1 Distance-dependent vocabulary (function-word suppression at long range) — **highest ratio**

fx2-cmix maintains four word streams and drops Conjunction/Article/Male/Female/
Adposition/AdverbOfManner from the longer ones (`fxcmv1.cpp:3681-3688`,
`README.md:30-35`), and the README credits the word-type work with "large amounts
of compression improvements". The transferable claim is not the POS tagger — it is
that **the vocabulary that should be counted at distance *d* shrinks as *d* grows**.
At *d* = 1 `the` is enormously informative; at *d* = 20 it is noise.

- Touches: `experiments/distance-similarity/`, and if it survives,
[[order-and-association#Order decays]].
- Measure: refit the distance-*d* tables with a per-*d* token mask (drop the top-*k*
by marginal, or drop tokens whose distance-*d* lift distribution is
indistinguishable from null) and compare held-out bpc and mode
interpretability at matched rank.
- Why cheap: it is a mask on an existing pipeline, and we already have the
per-distance machinery.
- Convention: clean. The mask is derived from a stated statistic, not fitted.



### 6.2 Final-stage calibration (an APM/SSE analogue)

`fxcmv1.cpp:4730-4754` maps (prediction, small context) → corrected prediction
through six chained adaptive probability maps. We currently emit
softmax(s(w)) and stop.

- Touches: [[naive-bayes-model#Inference]], plus a runner under
`experiments/predictive/`.
- Measure: bpc delta from a single calibration stage keyed on, say, (predicted
rank bucket, distance-1 context class). One number, cheap to get.
- Convention: this is a *fitted* stage. It must be spec'd as such, with its
parameters counted in [[naive-bayes-model#Transmission]] — which is exactly the
discipline fx2-cmix follows by putting its dictionary in the executable.



### 6.3 Hierarchical output code with mode-derived classes

The §3.5 conclusion, made concrete: cluster tokens by their mode loadings, use the
clusters as classes of a two- or three-level code, predict class then member.

- Touches: [[naive-bayes-model#The free normaliser]] and `#Inference`; a new
proposal document (do **not** fold it into [[hierarchical-modes]] — that
document is about the feature space, this is about the output space).
- Measure: held-out bpc versus flat softmax at matched rank, *and* Z-evaluation
cost, since removing the partition function is half the prize.
- Prior art to cite: Goodman's class-based softmax and Morin & Bengio's
hierarchical softmax should go into [[prior-art]] alongside the existing
Mnih & Hinton entry.
- Risk, stated up front: if the classes are not nameable, this is a pure speed
win with no interpretability gain, and should be judged as such.



### 6.4 Segregate the interlanguage-link tails

§2.4's trick, adapted. Move every trailing `[[xx:…]]` block to a contiguous region
and let the model see them densely.

- Touches: a new pre-pass alongside `src/NormalizeV3.jl`; spec'd in
[[tokenizer-score#Admissibility]]'s markup discussion, which already argues that
corpus artifacts should be handled analytically.
- Measure: exact bits before/after on enwik8 and enwik9, plus a byte-exact
round-trip test. Steal the self-signalling boundary (§2.4) rather than adding a
length field.
- Caveat that is *not* small: our model is **static**, so it does not benefit from
locality the way an adaptive one does. The gain would come from the merge score
seeing dense repetition of `[[fr:` etc., i.e. from better *tokens*, not from
better *adaptation*. That is a weaker mechanism and the experiment should be
designed to test it rather than assume it.
- Convention: reordering the byte stream is a real change to what "exact bits on
the exact enwik bytes" means. The permutation must be inverted exactly, and the
spec must say so.



### 6.5 Structural contexts a co-occurrence table cannot express

Bracket-type-and-distance (`fxcmv1.cpp:1852-1916`), first-character-of-line stack,
and table above-cell (`fxcmv1.cpp:1919-2066`).

- Touches: this is a genuinely new *kind* of conditioning for us — everything in
[[naive-bayes-model]] is a directed count at distance *d*. Adding a
non-distance context is a structural extension and needs its own spec section.
- Measure: as an extra slot in the additive score, with its own λ, fitted like the
others ([[naive-bayes-model#Slot discounts]]).
- Ratio is mid: the signal is real, the spec work is not trivial.



### 6.6 Per-context λ (mixing weights that depend on the context, not just the distance)

Our λ_d is one scalar per distance. fx2-cmix's entire architecture is "the weights
depend on a context". The minimal version: bucket λ_d by a coarse feature (inside
markup / in prose / in a table) and fit one λ per bucket.

- Touches: [[naive-bayes-model#Slot discounts]], `experiments/predictive/`.
- Measure: held-out bpc versus global λ_d; also check whether the fitted buckets
are interpretable, since that is our differentiator.
- Note this is a *gate*, so it is a mild form of the conjunction
[[hierarchical-modes]] wants — worth flagging in that document as a cheap
baseline the bilinear layer must beat.



### 6.7 Article reordering — **do not steal, and here is why**

This is the trick our project is structurally unable to use. Reordering pays for
fx2-cmix because its models are online-adaptive: adjacency keeps the match models
and mixer weights in a locally stationary regime. A **static counted model has no
position-dependent state at all** — the distance-*d* co-occurrence tables of
[[order-and-association]] are invariant under any permutation of the articles,
because permuting articles changes only the handful of adjacencies at article
boundaries. We would pay 201 KB (§2.3) for a permutation our model cannot see.

The one thing that *could* transfer is the reverse direction: our spectral
embedding is a candidate 1-D ordering, and offering it to an adaptive compressor
is a legitimate external validation of the embedding. That is an interesting
experiment about *our modes*, not a compression idea for *our compressor*, and it
should be framed that way.

### 6.8 Explicitly do not steal

Hardcoded corpus byte offsets (`fxcmv1.cpp:3837`, `3884`, `3119`); hardcoded
enwik9 line numbers (`misc.h:2-8`); hand-fitted per-map constant arrays
(`fxcmv1.cpp:3134-3139`); precomputed state tables (`states/nonstationary.cpp:3`);
PGO with a corpus-shaped profile and a fixed RNG seed
(`build_and_construct_comp.sh:6-7`); and the four hardcoded article exceptions in
the language-tail rule (`phda9_preprocess.h:437-443`). Every one of these is
rational under the Hutter Prize's rules and every one of them is precisely what
"code is reproducible from the specs" forbids. If we ever want a corpus-specific
constant, it must appear in a spec as a stated, justified number — not as a
literal in a conditional.

**And one structural warning.** An external hand-curated dictionary
(`dictionary/english.dic`, provenance unknown, §2.2) is the largest single
departure from our conventions on offer here. Our vocabulary is *derived*, by a
specified criterion, from the corpus itself, and its transmission cost is
accounted ([[naive-bayes-model#Transmission]]). Importing an external word list —
even as "just a warm start" — would break that chain. If it is ever tried, it must
be spec'd as an offline-fitted input with its bits counted, exactly as fx2-cmix
counts its 100 088.

---



## 7. Open questions this study could not close

1. **How much does the article reorder actually buy?** No ablation in the repo.
  `README.md:70-73` links external documents with improvement graphs; not
   fetched. Floor is 201 043 bytes; ceiling unknown.
2. **How large is the language-link stream on enwik9, and what fraction of the
  archive does it occupy?** Requires running the transform on a 1 GB corpus we do
   not have locally. Could not determine.
3. **Provenance and construction of** `english.dic`**.** No script, no frequency list,
  no note. Could not determine.
4. **Whether the** `&` **run-swap in** `hent9` **is genuinely dead code.** High-confidence
  read of `:303-334`, not verified by execution.
5. **Whether the four hardcoded language-tail exceptions are the complete set of
  enwik9 failures** for that rule, or merely the ones that surfaced. Could not
   determine without running.
6. **What the 461 model outputs decompose into by contribution.** The count is
  printed (`predictor.cpp:140`) but no per-model attribution exists in the repo,
   so "which of these tricks earns the bits" is unanswerable from source alone —
   which is itself the strongest argument for our interpretability bet.

