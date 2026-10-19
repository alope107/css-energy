# 07. HarfBuzz: the GSUB "CPU", its cost model, what's changing, and HarfRust

Scope: what HarfBuzz does with js-minus-js's CPU font from `hb_shape` down, where the ~21 ms per shaping goes, which
limits bind, and what changes between the HarfBuzz in Chrome 153 and the one in main. Blink's side (segmentation,
features, the `hb_shape_full` call, HarfRust in Blink) is chapter 06; release timing is chapter 09.

Code is cited as `hb:src/<file>:<line>` at **14.5.1-141 (`12ee77ee`)**, which Chrome 157 and main bundle. Chrome 153
bundles **14.3.1-10 (`dfdc088c`)**, 155 bundles 14.4.0-86. Chromium paths are from the src root at main `22b3b159`.

**How this was measured.** No C compiler is installed, so HarfBuzz was built from its amalgamated `harfbuzz.cc` with
`zig c++ -O2` (zig 0.17, clang-based) at the exact revisions Chrome ships, linked to a small driver that replays the
94 FizzBuzz shapings of the current CPU font (S = 32, the font `make font` builds today: 392 subtables per cycle; the
`build/f4cc_16.ttf` in the main checkout is older). A patched copy adds `rdtsc` around every top-level lookup
application and counters in the hot paths. Timings are interleaved A/B runs pinned to one E-core (CPU 14, steady,
~1.6× slower than a P-core) and cross-checked on a P-core; other agents shared the machine, so read ratios. Absolute
P-core baseline: 20.1–21.6 ms per shaping, matching BENCHMARKS §3's 20.6 ms. Scripts and builds:
`exp/07/{scripts,drv}` (§6). Labels: *(code)* read in source, *(measured)* run here, *(derived)* computed from
measurements, *(inference)*.

## Findings

1. **Where the time goes** *(measured; the split derived)*: per shaping, 3,768 lookup applications over a
   1,276-glyph buffer; the context matcher steps over **2.42 M glyphs, 84% of them skipped** by mark filtering, and
   1.72 M mark-set tests take the out-of-line "wide set" path. Walks ≈ 50–60% of the time, the fixed per-lookup
   scan ≈ 15%, rule and class matching the rest. The 20 `K3 gather` reverse-chaining lookups alone are **32.5%**.
2. **ENGINE_NOTES 28 needs one correction**: walk distance is counted in *buffer* glyphs, hidden ones included.
   Mark-filtering sets shorten rules, not walks; every hidden glyph between two context positions costs a
   mark-set test (2–6 ns). *(code + measured)*
3. **Half the HarfBuzz time is spent after the trap.** Only 52% of the 32 micro-cycle slots do work (the rest follow
   a trap), and a trapped cycle costs 94% of a running one. *(measured)*
4. **A GSUB lookup can halt the shaping.** A contextual lookup that recurses into itself trips
   `HB_MAX_NESTING_LEVEL` (64), sets `buffer->successful = false`, and every later *forward* lookup (GSUB and GPOS)
   becomes a no-op; reverse-chaining lookups still run. Blink renders the buffer as it stands (verified in Chrome 153).
   An abort lookup at the end of each micro-cycle cuts **29–30%** per shaping on FizzBuzz. *(code + measured)*
5. **The 16,384-subtable cap is per LookupList entry, not per run of a lookup.** One LookupList entry referenced by
   features in *different shaping stages* runs once per stage and is sanitized once. The default shaper has 2 GSUB
   stages (`rvrn`, then the rest); the Arabic shaper has 6 for features every glyph carries. Measured: the CPU font
   runs exactly **64 cycles** (default shaper) and **192 cycles** (Arabic-script code points) per shaping with the
   sanitizer budget of 32, every shaping matching the model; Chrome 153 runs a test lookup 2× (Latin) and 6×
   (Arabic). *(code + measured)*
6. **Chrome 155+ runs the CPU font 6–8% slower than 153** *(measured)*. Cause: HarfBuzz 14.4.0's mark-set bit-page
   change made the path for sets wider than 512 glyph ids an out-of-line call (`HB_NEVER_INLINE`); inlining it
   recovers most of it. Replacing that path with a flat per-set bitmap makes the font **24–27% faster** than main.
7. **Glyph renumbering** so that each lookup's mark set fits 512 ids moves 20.9 of 27.2 ms-weight of lookups onto the
   fast path and removes 44% of slow mark-set tests, but buys only ~5% (E-core; noise on a P-core): the expensive
   tests are in the few lookups with sets of 1,000–2,700 glyphs. *(measured)*
8. **HarfBuzz's "hot subtable" cache costs this font 5–6%** (an O(buffer) reset per lookup application, and 145 of 261
   chain subtables have input classes ≥ 15, which the 4-bit cache can't hold). *(measured with a patched build)*
9. **max_ops**: a FizzBuzz shaping uses 549 k of its 5.2 M budget (10.5%), ~77% of it from `move_to`, which 14.4.0
   started charging. Six stages at S = 41 would use ~4.2 M: the budget, not the sanitizer, becomes the next wall.
   *(measured + derived)*
10. **Contexts are not capped at 64**: only the *input* sequence is (`inputCount ≤ 64`); backtrack and lookahead take
   up to 65,535 glyphs, in HarfBuzz and in HarfRust. ENGINE_NOTES 27 is half right; the readback's 64-column limit
   isn't HarfBuzz's. *(code)*
11. **HarfRust** on the CPU font, standalone, same machine: **1.34× HarfBuzz's time at 0.14.0** (what Chromium
   links), **1.21× at HEAD** (October lookup-cache work). It mirrors HarfBuzz's design (same digests, mark-set page
   and out-of-line slow path, hot subtable), so the same font levers apply; it has no subtable cap. *(measured, code)*
12. **New in 157+: FeatureVariations 1.1** (`LookupVariationRecord`): per-feature lookup sets that are the *union* of
   all matching condition records. Not guarded by Chromium's build flags, and GSUB isn't sanitized by OTS. *(code)*

## 1. How it works

### 1.1 What the CPU font is, as HarfBuzz sees it

From `machine/cpu4.py`, `cpugen.py`, `otl.py` and the rebuilt font *(code + measured on the build)*:

| Item | Value |
|---|---|
| Glyphs / cells (buffer length) / distinct input code points | 7,009 / 1,276 / 840 (U+F0001…, supplementary PUA) |
| Distinct Lookups | 354: 233 library SingleSubst (`SET0…`, `ADD1…47`, `ADDM`, `PSET`, `P16_*`, `P256_*`, `PRAM`), 1 prologue, 118 per cycle, 2 tail (`epilogue`, `export`) |
| LookupList entries | 4,012 = 233 + 1 + 32 × 118 + 2 (each cycle Lookup referenced 32 times, ENGINE_NOTES 25) |
| Subtables referenced (sanitizer count) | 12,821 (392 per cycle); cap 16,383 → S ≤ 41 |
| Per cycle | 90 ChainContextSubst (261 subtables, all **format 2**, 7,957 rules), 23 ReverseChainSingleSubst (126 subtables), 5 SingleSubst (`MAP`) |
| Wrapping | every Lookup is ExtensionSubst (type 7) so payloads sit behind 32-bit offsets |
| Lookup flags | `UseMarkFilteringSet` (0x10) on 113 of 118 cycle lookups, 0 elsewhere; no IgnoreMarks/attachment types |
| GDEF | class 3 (mark) for every state glyph, class 1 for the `X.*` export twins; one mark-filtering set per contextual lookup = all glyphs of every glyph *type* the lookup touches (median 195 glyphs, max 2,739; only 38 of 113 span < 512 ids) |
| ClassDefs | all format 2; input classes up to 165, lookahead up to 36; rules average 1.8 backtrack, 3.2 input, 0.5 lookahead positions; up to 1,024 rules in one rule set |
| Coverage | format 2 (211 subtables) or 1 (50) |
| Features / script | `cv01` = prologue + 32 × cycle + tail; `cv02` = prologue + tail; `ssNN` debug features off in the page build; ScriptList has only `DFLT` |
| GSUB / GDEF size | 1.24 MB / 4.3 kB (woff2 70 kB) |

Micro-ops: an `A` stage is one ChainContext rule per (target, key combination) applying a nested `SET_x`; a `DA`
("dispatch") rule starts at a source glyph and applies nested ops at later positions of its input sequence; `RA` is
ReverseChainSingleSubst for leftward data flow (ripples); `MAP` a SingleSubst. The cache is 16 lines of 71 cells
(1,136 of the 1,276 cells; the core is 140); the gather (`K3 gather:G0…G19`, one lookup per data bit) ORs a bit
across the 16 lines by an `RA` ripple.

The readback font (`readback/mkfont2.py`) is ordinary fontTools output: feature `rclt` empty by default, one
FeatureVariations record per column (`SCAN` ∈ [j+0.5, j+1.5]) adding `CAP_j` (format 3, backtrack j or j+1),
`RPROP` (format 3 forward carry) and `LPROP` (reverse chain), plus a GPOS `kern` that cancels the sentinel.

### 1.2 From `hb_shape` to a lookup list

`hb_shape_full` → `hb_shape_plan_create_cached2` → `_hb_ot_shape`. The plan is built once per key and cached on the
face in a lock-free linked list that is searched linearly and never evicted (`hb:src/hb-shape-plan.cc:533-590`). The
key (`:159-185`, `hb:src/hb-ot-shape.hh:44-103`) is the segment properties (direction, script, language), each user
feature's **tag and value** and whether it is global, the shaper, and the OT key: the FeatureVariations record index
per table plus (new in 14.5) the resolved lookup-variation state. Coordinates themselves are not in the key: a
`SCAN` value that selects the same record reuses the plan; each distinct `cv01` value or column is one more plan
node. Flipping `cv01` 0/1 or stepping `SCAN` per pass therefore costs a list walk over ≤ 67 nodes, not a rebuild;
the first use of each value compiles a map over 4,012 lookup entries once. (Blink's own caches: 06 §1.3.) *(code)*

Feature collection for the default shaper (`hb:src/hb-ot-shape.cc:322-410`) *(code)*:

```
stage 0:  rvrn                                  ← enable_feature(rvrn); add_gsub_pause(nullptr)   (:329-330)
stage 1:  ltra ltrm frac numr dnom rand Harf HARF Buzz BUZZ abvm blwm ccmp locl mark mkmk rlig
          calt clig curs dist kern liga rclt  + every user feature (cv01 …)
```

`hb_ot_map_builder_t::compile` (`hb:src/hb-ot-map.cc:203-408`):
- **Feature merge** (`:232-259`): features are sorted by tag; duplicates merge, the **lowest stage wins**, a later
  global entry overrides value. So `font-feature-settings: "rvrn" 0` disables `rvrn` (max value 0 → skipped at
  `:287`), and a user feature never moves to an earlier stage than the shaper put it.
- **Mask bits** (`:269-343`): a global feature with value 1 uses the shared global bit 31; any other gets
  `min(8, bit_storage(max_value))` bits (`HB_OT_MAP_MAX_BITS 8`, `hb:src/hb-ot-map.hh:35`), allocated from bit 4
  (bits 0–2 are glyph flags) up to bit 30; features that don't fit are dropped silently.
- **Lookups per stage** (`:351-407`): for each stage, the lookups of every feature in that stage are appended, then
  **sorted by LookupList index and merged** (`:381-397`): the same index twice *in one stage* runs once (hence the
  repo's aliasing), but the same index in two stages runs twice.

At shape time (`hb:src/hb-ot-layout.cc:2042-2104`), for each stage, for each lookup: get the per-index accelerator
(lazily created, one per LookupList entry, so 32 accelerators for one aliased cycle lookup), test the lookup's
coverage digest against the buffer's digest, apply, then run the stage's pause function.

### 1.3 Applying one lookup

`apply_string` (`hb:src/hb-ot-layout.cc:2005-2040`): GSUB forward lookups always run "out of place"
(`clear_output()` … `sync()`), but while no lookup changes the glyph count `out_info == info` and nothing is copied;
the CPU never changes the count, so it is effectively in place. ReverseChain lookups are in place by definition.

```
apply_forward (:1949)                          apply_backward (:1983)
  hot = accel.cache_enter()   ← O(len) reset     for idx = len-1 … 0:
  while buffer->successful:                         if digest ∧ mask ∧ props(cur): accel.apply(c, false)
    skip j while ¬(digest.may_have(g)           (no successful check, no hot cache)
             ∧ mask & lookup_mask
             ∧ check_glyph_property(g))  ← mark-set test
    accel.apply(c, hot) or next_glyph()
```

`hb_ot_layout_lookup_accelerator_t` (`hb:src/hb-ot-layout-gsubgpos.hh:6152-6260`): an array of the lookup's
subtables (Extension unwrapped at build time, so wrapping costs nothing at run time), each with its own coverage
digest; `apply` tries them in order until one applies (`:6213-6247`; a one-subtable lookup skips the retest).
The digest (`hb_set_digest_t`, three 64-bit masks at shifts 4, 0, 6) is the cheap first filter. Lookup-level
skipping (`digest.may_intersect(buffer->digest)`) never fires for the CPU: the buffer digest only grows during a
shaping and 1,276 distinct glyphs saturate it (11 skips per shaping, measured).

### 1.4 Matching a ChainContext format 2 rule

`ChainContextFormat2_5::_apply` (`:5566-5622`): coverage of the current glyph (cached), its input class picks a
rule set, then `ChainRuleSet::apply` (`:4926-5079`):

- Rule sets with ≤ 4 rules take the plain loop: every rule runs `chain_context_apply_lookup` (`:4541-4590`), which
  matches **input, then lookahead, then backtrack**, each through a skipping iterator.
- Larger sets take the fast path: look at the next one or two *visible* glyphs once, reject rules whose first
  input/lookahead class differs (and skip runs of rules with the same failing first class), and, since 14.5, reject
  the whole set if the first glyph's class isn't in a 64-bit per-set digest (`hb_ot_layout_ruleset_digest_t`,
  `:1589`). Survivors run the full match.
- The CPU: 30.3 k rule-set entries per shaping, 87% via the plain loop; 59.1 k full rule attempts, ~93% failing.
  *(measured)*

The skipping iterator (`:899-1100`): `next()`/`prev()` step one buffer glyph at a time; for each,
`matcher_t::may_skip` (`:871`) calls `check_glyph_property` (`:1282`): if the glyph is a mark and the lookup uses a
mark-filtering set, `gdef_accel.mark_set_covers(set, gid)`. Hidden glyphs are skipped, so a rule that is two
positions long in the *view* still walks every glyph between them in the buffer.

`mark_set_covers` (`hb:src/OT/Layout/GDEF/GDEF.hh:1044-1070`, since 14.4.0):

```cpp
const auto &bitmap = mark_glyph_set_bitmaps.arrayZ[set_index];
if (likely (bitmap.bias != HB_SET_VALUE_INVALID)) {          // set spans < 512 gids: exact bit-page
  hb_codepoint_t biased = glyph_id - bitmap.bias;
  return biased < hb_bit_page_t::PAGE_BITS && bitmap.u.page.get (biased);
}
return mark_set_covers_slow (set_index, glyph_id);          // HB_NEVER_INLINE: digest, then Coverage bsearch
```

In 14.3.1 the whole test was an inlined `digest.may_have(g) && table->mark_set_covers(...)`.

On a match, `apply_lookup` moves to each LookupRecord position (`hb_buffer_t::move_to`, `hb:src/hb-buffer.cc:469`,
a memmove over the skipped glyphs, forward and back) and recurses (`recurse`, `:1103`): nesting −1, `max_ops` −1,
then the nested lookup at that glyph. Every successful context match also marks `unsafe_to_break` over the matched
span (`hb:src/hb-buffer.hh:494-510`, skipped when the span exceeds 255 glyphs); failed matches only mark
`unsafe_to_concat` when the buffer asks for it, and Blink doesn't (06 §1.6).

### 1.5 Caches, and which help this font

| Cache | Where | Scope | For the CPU font |
|---|---|---|---|
| Hot subtable | one subtable per lookup (largest `cache_cost` = input + lookahead ClassDef bsearch depth) | `cache_enter` writes `syllable = 255` on **every glyph** (`:3044-3066`), then input class in the high nibble, lookahead class in the low nibble (`get_class_cached1/2`, `:1841-1875`), classes < 15 only | every format-2 subtable qualifies; 145 of 261 have input classes ≥ 15; 3.66 M byte writes per shaping. Disabling it: −4.7% (E) / −6.2% (P) *(measured)* |
| External caches | first 8 subtables of each lookup (`:1531`) | coverage: 256-entry 1-bit `hb_cache_t<14,1,8>`; input/lookahead class: 256-entry `hb_cache_t<16,8,8>`; per-rule-set first-class digest | direct-mapped on gid & 255; glyph ids < 16,384 OK |
| GDEF glyph props | per face | 512-byte cache | all state glyphs are marks |
| Mark-set bit-page | per set, since 14.4.0 | exact if the set spans < 512 ids | 38 of 113 sets |

Since a cache helps only when a lookup sees the same glyphs repeatedly, and a CPU lookup application touches ~15
glyphs out of 1,276, the per-application set-up costs (scan, hot-cache reset) dominate the savings.

### 1.6 ReverseChainSingleSubst

`hb:src/OT/Layout/GSUB/ReverseChainSingleSubstFormat1.hh:184-230`: coverage of the current glyph (uncached bsearch),
then `match_backtrack` and `match_lookahead` with one Coverage per position (`match_coverage`, uncached), then an
in-place replace. `apply_backward` visits every glyph, has no hot cache, and **does not stop when the buffer has
failed**. Not callable as a nested lookup (`nesting_level_left != HB_MAX_NESTING_LEVEL` → false). *(code)*

### 1.7 Limits

`hb:src/hb-limits.hh`, unchanged by Chrome (no `-D` overrides in `third_party/harfbuzz/BUILD.gn:475-530`):

| Limit | Value | What it does to the CPU |
|---|---|---|
| `HB_MAX_CONTEXT_LENGTH` | 64 | caps the **input** sequence only (`inputCount > 64` → rule never matches, `hb-ot-layout-gsubgpos.hh:1928, 4552`). Backtrack and lookahead arrays have uint16 counts and no cap (`match_backtrack` `:2165`, `match_lookahead` `:2203`). HarfRust HEAD explicitly keeps > 64-glyph contexts working (`f325ef9`). |
| `HB_MAX_NESTING_LEVEL` | 64 | at 0, `recurse()` sets `buffer->successful = false` (`:1105-1109`): see §2.2 |
| `max_ops` | `max(len × 4096, 65536)` per shaping (`hb-buffer.cc:326-340`) = 5.23 M at 1,276 glyphs | charged by `recurse` (1 each), `unsafe_to_break` spans ≤ 255, cluster merges, and since **14.4.0 `move_to`** (`cf30f712e`). FizzBuzz: 549 k per shaping = 10.5%: 118 k spans, 9.7 k recursions, ~421 k `move_to` *(measured / derived)*. Exhaustion = silent `successful = false`. |
| `HB_SANITIZE_MAX_SUBTABLES` | 0x4000 | `visit_subtables` (`hb-sanitize.hh:148`) adds each Lookup's subtable count, **once per LookupList entry**, cumulative over the GSUB; `< 16384` passes; past it the whole GSUB is discarded (prior survey). Extension subtables count once (`Lookup::sanitize`, `hb-ot-layout-common.hh:1410-1418`); the inner subtable isn't counted again. |
| Sanitizer ops | `clamp(bytes × 64, 16384, 2³⁰)` (`hb-sanitize.hh:100-115, 227-245`) | 79 M for this GSUB; every aliased copy re-checks its bytes, so ~S × cycle bytes; binds only past S ≈ 64 |
| GSUB sanitize | eager, on first use of the face's GSUB accelerator (`hb-ot-layout-gsubgpos.hh:6655-6676`) | `lazy_some_gpos` exists only for GPOS |
| GPOS | separate table, separate sanitize context, own 16,384 budget | GPOS lookups can't change glyph ids, so no micro-ops; only advances |

FeatureVariations: version 1.0 picks the **first** matching record and substitutes feature tables
(`find_index`, `hb-ot-layout-common.hh:5747-5762`). Version 1.1 (`LookupVariationRecord`, `:5675-5730`; shaping since
`2c05df744`, in 14.5.1-141) adds per-feature `FeatureLookupsTable`s: **every** matching `LookupConditionRecord`
adds its lookups (a set: deduplicated, sorted), optionally on top of the feature's default lookups
(`ADD_DEFAULT_LOOKUPS`). The resolved state is part of the plan key. All of it reads the same LookupList, so no
FeatureVariations form changes the subtable count. *(code)*

### 1.8 The measured cost model

Per-lookup profile, FizzBuzz, S = 32, HarfBuzz 14.5.1-141, E-core (34.0 ms per shaping; P-core ≈ 0.6×). Sum of the
per-lookup times = 34.04 ms = 99.8% of the shaping. *(measured)*

| Stage group | ms | % | Notes |
|---|---|---|---|
| `K3 gather` (20 bit lookups + `GFpass`, RA) | 11.06 | 32.5 | ~0.55 ms each; 17 applications per pass, ~50 glyph steps each |
| `K3 write` (`VALw` 18 subtables 640 rules, `TAGw`, `WS0-3w`, `VDw`) | 3.65 | 10.7 | `VALw` alone 2.0 |
| `K5 sppc` (SP/PC updates, ripples) | 3.00 | 8.8 | |
| `K2 MDW`, `K2 MAR` (address/data arithmetic) | 4.03 | 11.8 | `MDW.1`: 1,534 rules, mark set 2,739 glyphs |
| `K3 wh`, `any`, `gs`, `gsc`, `eq`, `init`, `alloc`, `we`, `decide`, the 11 bus broadcasts | 6.52 | 19.2 | buses 0.16–0.23 each |
| everything else (K0 ROM fetch 0.54, K1, K4, K5 rest, prologue/epilogue/export) | 5.78 | 17.0 | |

Counters per shaping *(measured)*:

| Quantity | Per shaping |
|---|---|
| Lookup applications | 3,768 (11 skipped by the lookup digest) |
| Glyphs offered to a lookup (passed digest, mask, props) | 71.4 k (58.9 k forward, 12.6 k reverse) |
| Successful top-level applies / nested lookup calls | 4.1 k / 9.7 k |
| Full rule match attempts | 59.1 k |
| Iterator steps (`next` + `prev`) | 2.42 M, of which skips 2.03 M (84%) |
| Wide-set mark tests (`mark_set_covers_slow`) | 1.72 M |
| Uncached ClassDef lookups | 199 k |
| Hot-cache resets | 2,871 lookups × 1,276 glyphs |

Fixed cost of a lookup application that finds nothing: **~1.4 µs** on the E-core (1,276 digest tests ≈ 1.1 ns each,
plus `clear_output`/`sync`), measured on the cycle lookups whose glyphs never appear; × 3,768 ≈ 5.3 ms ≈ **15%**.
Least-squares fits of lookup time against the counters are poorly conditioned (R² 0.35–0.8); they put walk steps at
~6–8 ns each including the mark-set test and attribute 50–60% of the time to walks *(derived)*. The controlled
experiments in §2 are the firmer evidence.

**Reconciling with the repo.** ENGINE_NOTES 28 ("cost ≈ rules tried × context walk distance") holds if distance is
measured in buffer glyphs: mark filtering keeps the *rules* short (a source 40 cells away is the next view glyph),
but HarfBuzz still steps over the 40 hidden glyphs, each costing a mark-set test, and a failed rule pays its walk
again. PRIMITIVES' 40–44 ns per glyph for an `rsub` counter increment is three lookup passes (MAP, rsub, MAP;
`survey/exp/aat/mkcounter.py`) over dense digits, ≈ 13–15 ns per glyph per pass, the same as a gather lookup here
(~16 µs per application over 1,276 glyphs ≈ 13 ns per buffer glyph per pass, with only 17 ripple targets). morx's
9.6–10.7 ns is one state-machine visit per glyph with no context re-walk and no per-glyph filter chain.

## 2. What it means for the projects

css-physics and paint don't shape anything heavier than text; this chapter is about js-minus-js (CPU font and
editor readback). Shaping is ~43 ms of a ~148 ms CPU frame (BENCHMARKS §6), and every shaping is a layout pass, so a
change can win twice: less HarfBuzz time per shaping, or fewer shapings.

### 2.1 Where to cut, in order of what the profile says

1. **Post-trap cycles (~46% of HarfBuzz time, derived).** 48% of the 3,008 slots in FizzBuzz's 94 shapings follow a
   trap; a shaping that starts trapped costs 94% of a normal one (31.2 vs 33.0 ms) *(measured)*. The lookups still find
   covered glyphs and walk; only the rules' gates (`CJ`, `OKJ`) fail, after the walk. → §2.2.
2. **Wide mark-filtering sets.** 1.72 M slow tests per shaping. Font-side: keep sets narrow (§2.4); HarfBuzz-side:
   §5.
3. **The gather ripple (32.5%).** Each `Gpass` step walks from one line's `G_b` to the next line's (71 glyphs, all
   but one hidden), and all 20 bit lookups run in every micro-cycle although only 34.5% of slots read RAM
   *(measured with `uarch4`)*. → §2.5.
4. **The scan floor (15%)**: 1.4 µs × lookups × S, proportional to buffer length. Fewer, wider lookups or a
   shorter line pay directly.
5. **The hot-subtable cache (5–6%)**: unavoidable for format-2 subtables; formats 1 and 3 have no `cache_cost`
   and skip it (inference: not worth rewriting for).

### 2.2 Halting the shaping on a trap

Mechanism *(code)*: a ChainContext lookup whose only rule matches the control glyph `C` in a trap state and whose
LookupRecord points at **its own LookupList index** recurses 64 times at the same glyph, then `recurse()` sets
`buffer->successful = false` (`hb-ot-layout-gsubgpos.hh:1103-1112`). From then on:
- the rest of that lookup's pass stops (`while (buffer->successful)`, `hb-ot-layout.cc:1955`) and `sync()` resets the
  output (`hb-buffer.cc:416-440`); with `out_info == info` the glyph array keeps the state reached so far;
- every later forward lookup returns at once, in GSUB and GPOS;
- **reverse-chaining lookups keep running** (`apply_backward` has no check);
- default positioning still sets hmtx advances (`hb_ot_position_default`), so widths are real;
- `hb_shape_full` still returns true; the buffer is flagged (`hb_buffer_allocation_successful` = 0), and Blink
  ignores both (`harfbuzz_shaper.cc:353`, 06 §5).

Verified *(measured)*: toy font (`exp/07/abort/`): lookups [abort, b→c, reverse b→d], text "ab": HarfBuzz C API
gives `a d` with `successful=0` (without the abort lookup: `a c`); **Chrome 153 renders 500 px vs 400 px** for
"ab", 900 vs 700 for "bab", i.e. the aborted buffer, reverse lookup applied, forward one not. uharfbuzz raises
`MemoryError` instead (it checks the flag), so `hbtest.py` can't use this.

On the CPU font (abort lookup appended to every cycle, firing on `C ∈ ('T', *)`; timing only, because the `export`
tail no longer runs after a halt): **0.711× (E) / 0.696× (P) per shaping** *(measured)*. What remains after the halt
is the RA lookups (gather, `any`, `GFpass`: ~0.38 ms per remaining cycle); if they found nothing to do after a
trap, the derived figure is ~0.52×.

To make it real, js-minus-js would need: the readback to read the state glyphs directly (advances on the state
glyphs instead of an `export` pass at the end, or an export folded into each cycle's tail), the halt at the end of
a cycle (so the state is a clean architectural state), and gather/any cells left uncovered at cycle end so the RA
lookups idle. Risks: it relies on error handling (an upstream change to stop reverse lookups too would only help;
a change to clear the buffer on failure would break it), and **under `HarfRustShaping` in 157+ the HarfRust bridge
returns false on a failed buffer and Blink then draws code points as glyph ids** (`hb:src/rust/shape.rs:430-433`, 06
§5 bug 1). In 153 the bridge copied the glyphs regardless (measured: same 500/900 px with the flag).

### 2.3 More micro-cycles than the cap allows

The cap counts LookupList entries; the shaper's stages re-run them. `rvrn` sits alone in stage 0 for every script,
is on by default, and can be switched off from CSS (`"rvrn" 0` merges into it with max value 0). So referencing the
prologue and the 32 cycle copies from `rvrn` and the cycles and tail from `cv01` runs 64 cycles per shaping with
12,821 subtables *(measured: `variant.py rvrn`, every FizzBuzz shaping equal to `uarch4` with S = 64, output
correct)*. Gating becomes `font-feature-settings: "rvrn" var(--go), "cv01" var(--go)`.

The Arabic shaper (`hb-ot-shaper-arabic.cc:184-240`) adds pauses after `stch`, after `ccmp`/`locl`, after each of
the seven joining-form features, after `rlig` (Arabic only) and after `calt`. Features every glyph carries are in 6
stages: `rvrn` | `stch` | `ccmp`+`locl` | `rlig` | `calt` | `liga`+`clig`+user. Test font with one counter lookup
referenced from all of them: uharfbuzz and **Chrome 153 apply it 2× for Latin/Hebrew/Thai and 6× for Arabic**
(`ب`, `ﭐ`) *(measured, `exp/07/stages/`)*. The CPU font with its 840 input code points remapped to Arabic-script
code points (1,248 usable: ccc 0, no canonical decomposition, not format/mark) and the cycle copies referenced from
those six features ran **192 cycles per shaping**, every shaping matching the model *(measured, uharfbuzz)*.
The other multi-stage shapers (Indic 5+ pauses, USE 8, Myanmar 4, Khmer 3) form syllables, reorder and insert dotted
circles, so they'd rewrite the state; Arabic only joins, and only letters with a joining type.
Requirements: empty `isol`…`init` features in the font (otherwise the Arabic fallback shaper may synthesize
lookups from the cmap), an RTL run (Blink reverses it visually; span widths are unchanged), and 06's segmentation
must keep the line one Arabic run (untested in a page).

Is more S worth it? FizzBuzz takes 94 shapings at S = 32, 80 at 64 and 80 at 192: traps end shapings
(4.6 steps per shaping). BENCHMARKS §1 models −24% suite shapings at S = 64. Without a halt, a 64-cycle shaping costs
1.94× (E) / 1.97× (P); **with the halt, 1.12×** *(measured, `v_rvrn_abort`)*. So the halt is what makes larger S pay:
80 × 1.12 = 0.95× FizzBuzz HarfBuzz time and 15% fewer layout passes. Beyond S ≈ 64 the gain is small unless traps
get rarer. max_ops caps how far: 549 k per 32 cycles → ~300 cycles per shaping at this line length *(derived)*.

### 2.4 Mark-set width

The set test is a one-page bitmap only if all of a set's glyph ids lie within 512. Glyph ids are internal (the page
uses code points U+F0000 + gid via the cmap), so the generator may number glyph types in any order. A seeded greedy
+ local search over type order (`scripts/renum.py`; seed: `L.BD*`, then per digit `L.GS_j`, `L.VAL0-3_j`, then
`L.G*`, `MDRB*`, `MOP`) raised the ms-weight of lookups with page-fit sets from 7.4 to 20.9 of 27.2 and cut slow
tests from 1.72 M to 0.96 M per shaping; the font verified exactly against the model; **time 0.952× (E), within
noise on a P-core** *(measured)*. The remaining slow tests sit in a few lookups with 1,000–2,700-glyph sets (`K2
MDW.1` 2,739, `K2 MAR.1` 2,140, `K5 loads` 1,908, `K5 fp` 1,184); there the digest passes often and a Coverage
bsearch follows. Splitting those lookups so each sees fewer glyph types is the font-side lever; a flat bitmap in
HarfBuzz (§5) is the general one (0.825× on top of the renumbered font).

### 2.5 The gather ripple

All 20 `G_b` cells per line start at 0 (`K3 init`), which is in each gather lookup's coverage, so every gather
lookup does its full walk in every cycle. Two independent cuts *(derived from the profile)*:
- **Gate it**: keep idle `G` cells in a value outside the coverage unless the cycle reads RAM (34.5% of slots) →
  (11.06 − 0.9) × 0.655 ≈ 6.7 ms of 34, **−20%**. Arming costs a lookup or a wider `GScopy` dispatch.
- **Shorten the walk**: the `Gpass` step joins line k to line k+1, 71 buffer glyphs apart. A layout where the 16
  lines' `G_b`/`GS_j` cells are adjacent shortens it ~10× but lengthens the per-line ops; any layout is a compromise
  across stages (ENGINE_NOTES 28's digit-major layout made the same trade for registers).
- Or a forward ripple (the core after the lines): a forward lookup sees already-substituted glyphs in its backtrack,
  so one pass propagates rightward. Same walk length; avoids RA's uncached per-position Coverage tests and makes the
  lookup subject to the halt (§2.2).

### 2.6 Readback font

- One plan per `SCAN` value (record index in the key) per face, kept forever: 65 small plans. *(code)*
- `CAP_j` uses backtrack `j`/`j+1`; HarfBuzz doesn't cap backtrack at 64, so the 64-column limit is the generator's
  choice. A 100-column scan would walk ≤ 100 glyphs per capture. *(code; untested)*
- FeatureVariations 1.1 (157+): several axes each adding their own lookups, unioned. *(code; untested; fontTools
  support for writing 1.1 unknown)*

### 2.7 Corrections to the repo's notes

- **ENGINE_NOTES 26**: the cap is HarfBuzz's sanitizer, counted per LookupList entry including the library,
  prologue and tail lookups, and past it the whole GSUB goes (prior survey). Add: it binds *entries*, not runs;
  stages multiply runs (§2.3).
- **ENGINE_NOTES 27**: "contexts are capped at 64 glyphs" → the *input* sequence is; backtrack and lookahead aren't.
- **ENGINE_NOTES 28**: walk distance is in buffer glyphs, hidden glyphs included (§1.8).
- **ENGINE_RESEARCH Q1** ("max_ops is charged only on nested lookup calls and cluster merges"): also `unsafe_to_break`
  spans and, since 14.4.0, `move_to`; the CPU uses 10.5% of the budget.
- **PRIMITIVES P9 / 09-roadmap's "~24% slower" for HarfRust**: that was end to end; per shaping, 06 measured 1.65×
  in Chrome 153 (HarfRust 0.12), and standalone 0.14.0 is 1.34×, HEAD 1.21× (§3.3).

## 3. What's changing

### 3.1 Versions

| Chrome | HarfBuzz | Relevant to the CPU font |
|---|---|---|
| 153 (tests) | 14.3.1-10 `dfdc088c` | baseline: **fastest of the three for this font** |
| 155 stable | 14.4.0-86 | mark-set bit-page with out-of-line wide path (`24b368ec1`), `move_to` charged to max_ops (`cf30f712e`), single-subtable digest retest skipped (`40949cc70`), saturating positions |
| 157 beta, 158 main | 14.5.1-141 `12ee77ee` | + per-RuleSet first-class digests (`724ef405f`), cached contextual input/lookahead classes (`be67d9612`), second-glyph lookup digests (`087e43231`), FeatureVariations 1.1 shaping (`2c05df744`), beyond-64k format work (compiled out) |
| next roll | 14.6.0+ (HEAD 14.6.0-105) | compact lookup-variation plan keys (`1b352dfc0`), Coverage cache fix for out-of-range keys (`2994c4d0a`), code sharing between table widths; nothing that changes this font's hot paths (the GDEF slow path is still `HB_NEVER_INLINE` at HEAD) |

Measured on the CPU font, interleaved, E-core, ratio to 14.5.1-141 *(measured)*:

| Build | Ratio (median of 8) |
|---|---|
| 14.3.1-10 (Chrome 153) | 0.919 (P-core: 0.944) |
| 14.4.0 / 14.5.0 / 14.5.1 tags | ~0.97 / ~1.00 / ~0.99 (3 rounds each, noisy) |
| 14.5.1-141 with the slow path inlined | 0.928 (P: 0.963) |
| 14.5.1-141 with flat bitmaps for wide sets | **0.760** (P: **0.728**) |
| 14.5.1-141 without the hot-subtable cache | 0.953 (P: 0.938) |

So Chrome 155+ makes the CPU ~6–8% slower per shaping than the 153 the repo tests on; the repo's benchmarks will
drift when the test browser moves. Absolute caveat: Chrome builds HarfBuzz with clang, ThinLTO and PGO; zig's clang
`-O2` won't match, ratios should.

Chromium's build (`third_party/harfbuzz/BUILD.gn:475-530`) defines `HB_NO_BORING_EXPANSION` (now unused by
HarfBuzz) and `HB_NO_VAR_COMPOSITES`; beyond-64k needs `HB_EXPERIMENTAL_API` and stays off; the WASM shaper sources
are in `unused_sources`; `hb-gpu`/raster/vector aren't built. FeatureVariations 1.1 has no guard, so it ships with
157. *(code)*

### 3.2 In flight upstream

Open HarfBuzz issues touching this area (GitHub, 2026-10-18) *(docs)*: #5936 "unified work-counter design" (one
budget object across subsystems; could change what `max_ops` counts), #6226 (a hieroglyph font hitting shaping
limits; Behdad points at the `max_ops` formula), #6230 (HarfRust bridge overhead for Chrome: "experiments testing
`hb-harfrust` shaper in Chrome", ~10% slower on most workloads, worse on tiny CJK runs), #6062 (`UNSAFE_TO_CONCAT`
semantics). No open PR touches GSUB application or mark sets.

### 3.3 HarfRust

Architecture *(code, `$SP/src/harfrust` at `f325ef9`)*: a Rust port tracking HarfBuzz 14.5.1, parsing through
read-fonts on demand with **no sanitize pass** (so no subtable cap, the reason it's interesting here), a per-lookup
`CachedLookup` with the same coverage digest, `digest_second`, hot subtable and `MAX_CACHED_SUBTABLES = 8`
(`ot/lookup/build.rs:23-110`), a GDEF `MarkGlyphSetBitmap` with the same one-page/digest split and an
`#[inline(never)]` slow path (`ot/mod.rs:100-140, 247-256`), the same `max_ops`, nesting and context limits, the same
`successful` handling (`ot/apply.rs:869-881`, forward loop `while ctx.buffer.successful`). So every font-side lever
above applies to it, and the flat-bitmap fix would too.

Speed on the CPU font, standalone `hr-shape -n` vs the C++ driver, same texts and core *(measured; Rust 1.99.1 + zig
linker, `exp/07/hr/`)*: HarfBuzz 33.3 ms, **HarfRust 0.14.0 44.5 ms (1.34×)**, **HEAD 40.4 ms (1.21×)**. HEAD's
gain comes from the 2026-10-14/15 series that caches parsed lookups with their tables and shares the context walk
(`9550595`, `ab6f70d`, `510828d`, `041ba83`). Outputs are identical. Why slower *(inference)*: the algorithms are
the same, so the gap is per-operation overhead (read-fonts' big-endian, bounds-checked access and on-demand parsing
where HarfBuzz reads sanitized memory directly); HEAD's gain from caching parsed lookups fits that. Chromium main
links `harfrust v0_14` (`cargo_pkg_version = "0.14.0"`) behind `HarfRustShaping` (status `test` in 155, 157 and
main; no status in 153). Also in flight: `harfrust_capi`, an `hr_`-prefixed C API "mirroring HarfBuzz" with an
`hr-hb.h` drop-in header and branches named `capi/chromium-ot-queries` and `capi/skia-*`, i.e. groundwork for using
HarfRust without HarfBuzz around it.

## 4. Ideas

Ranked by expected value × confidence. Speedups are per shaping unless stated.

1. **Halt on trap** *(code-backed; measured 0.70×; derived 0.52× if RA lookups idle after a trap)*. §2.2. Cheapest
   next experiment: give state glyphs their readback advances (drop `export`), add the abort lookup, rerun
   `hbtest.py` with a C-API runner (uharfbuzz refuses failed buffers) and the CPU-only page in Chrome 153.
2. **Stage multiplication for S** *(code-backed; measured exact at 64 and 192 cycles; Chrome toy measured)*. §2.3.
   With the halt: FizzBuzz 0.95× HarfBuzz time and −15% shapings (−24% suite-wide modelled at S = 64). Cheapest
   experiment: the `rvrn` variant on the CPU-only page (`"rvrn" var(--go)` gating), then L5.
3. **Upstream: flat bitmaps for wide mark-filtering sets** *(measured 0.73–0.76×; also fixes the 155+ regression)*.
   A user-filed HarfBuzz issue with this font as the benchmark; HarfRust has the same structure (§5).
4. **Gate the gather on RAM reads** *(derived −20%)*, and the write stages on writes (12% of slots) the same way.
5. **Narrow the big mark sets** *(derived from the renumbering result: the remaining 0.96 M slow tests cost ~5 ms
   on the E-core)*: split `K2 MDW.1`/`MAR.1`/`K5 loads`/`fp` by digit so each lookup's view holds fewer glyph types,
   then renumber (0.95× already measured for renumbering alone).
6. **Shorter state line** *(inference)*: the floor (15%) and the hot-cache reset scale with the 1,276 glyphs; the
   cache's 1,136 glyphs are worked on mainly by the K3 stages. Fewer lines (N < 16) trade misses for speed;
   `traps.py` models it.
7. **Feature values as an input channel** *(code-backed, untested)*: a global feature with value N (≤ 255) makes
   any AlternateSubst under it pick alternate N (`AlternateSet.hh:49-65`), nested ones included, since the index
   comes from the *calling* lookup's mask. `font-feature-settings: "cv03" var(--x)` would inject a byte without
   changing the text; each value is one more cached plan.
8. **FeatureVariations 1.1 toggles** *(code-backed for 157+, untested)*: k independently axis-gated lookup groups
   with k records instead of 2^k feature-table substitutions.
9. **Format 3 or 1 for the hottest small lookups** to avoid the hot-cache reset *(inference; ≤ 5% ceiling, measured
   by disabling the cache)*.
10. Negative results: **GPOS** can't host micro-ops (no glyph changes; separate 16,384 budget usable only for
    advance arithmetic); **ExtensionSubst** neither adds to the count nor costs at run time; **FeatureVariations**
    can't relieve the cap (one LookupList); lookup-level digest skipping can't fire at this buffer size;
    **ligature- or multiple-substitution state machines** change the glyph count, which forces a separate output
    buffer and copies for the rest of every such pass (`make_room_for`), on top of the same walks *(inference)*.

## 5. Possible bugs, upstream issues, open questions

**Performance regression, HarfBuzz 14.4.0+** *(measured)*: `24b368ec1` ("Answer mark-filtering-set queries from a
cached bit-page") made the test for sets spanning ≥ 512 glyph ids a `HB_NEVER_INLINE` call
(`hb:src/OT/Layout/GDEF/GDEF.hh:1062`). Fonts with wide mark-filtering sets lose 6–8% against 14.3.1 (this font:
0.919× → 1.0); inlining recovers it; a flat per-set bitmap over `num_glyphs` (110 words per set here, ~100 kB for
118 sets) makes it 0.73–0.76×. Same structure in HarfRust (`ot/mod.rs:247`). Not a correctness bug; a candidate
upstream report with `exp/07/v_base.ttf` + `texts_fizz.txt` as the benchmark.

**`apply_backward` ignores `buffer->successful`** (`hb:src/hb-ot-layout.cc:1983-2003`): after a `max_ops` or nesting
failure, forward lookups stop but reverse-chaining lookups keep substituting. Inconsistent rather than wrong (no
spec covers failure); §2.2 depends on the forward half.

**Failure under HarfRust in 157+** (adds to 06 §5 bug 1): `hb:src/rust/shape.rs:430-433` returns false whenever the
HarfRust buffer isn't `successful`, which a valid font reaches through `max_ops` or nesting (e.g. #6226's font),
not only malformed ones; Blink then commits code points as glyph ids. 153's bridge copied the partial result
instead (measured). *(code; 157 not run)*

Open questions:
- Whether Chrome's PGO/LTO build changes the 153 → 157 ratio (zig `-O2` here).
- The Arabic-script CPU in a real page: does `SegmentText` keep a 1,276-character Arabic-script line one run, and
  what does bidi do to the span readers? (06's territory.)
- How much of the halt's remaining cost a forward gather would remove (estimate 0.52× total).
- Exact `max_ops` split: `move_to` was inferred as the remainder (no direct counter).

## 6. Reproducing

Scripts are under `exp/07/` (relative to `survey/chromium/`). Builds, fonts, the js-minus-js copy and the Rust
toolchain are not committed; the scripts recreate them in a scratch directory (`SP` in them):
- `repo/` copy of js-minus-js; `img_fizz.json` from `compiler/mkimage.py --ram tests/suite/fizzbuzz.js`.
- `scripts/variant.py img out.ttf [abort|rvrn|arab|S=n]` builds font variants (identical GSUB/GDEF to `make font`
  without options); `ORDER=order.json` renumbers; `verify.py img font S_eff [feat] [dump] [cmap]` checks every
  shaping against `uarch4` and dumps texts.
- `scripts/buildrev.sh <rev>`, `buildvar.sh <name> <patch>` build HarfBuzz drivers with `python3 -m ziglang c++`
  (`PYTHONPATH=py`); `patchvar.py` holds the `inl`, `flat`, `nohot` patches; `patchprof.py` the profiler.
- `drv/drv_<v> font texts reps` times; `drv/drv_pt`/`drv_pc` profile; `scripts/anal.py`, `fit.py` aggregate.
- `scripts/ab.py core rounds font texts drvA drvB…` and `abf.py` (fonts) run interleaved A/B.
- `abort/`, `stages/` hold the Chrome 153 probes (`node probe.js …`); `hr/` the HarfRust builds
  (`RUSTUP_HOME`/`CARGO_HOME` under `rust/`, linker `hr/zigcc`), `scripts/hrtime.py` the timing.
