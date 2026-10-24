# RAM: a catalog of ways to build it

Every way found to hold a word, find it by a computed address, and read it in time, for a RAM that could replace
`machine/memtree.py` (ARCHITECTURE §1 "RAM on the page", §3.2). Each entry says what it is, what was measured (here, or
where), and a verdict. Probes are in this directory (§ Reproducing). Headless Chromium 153.0.8010.12 on the mini PC,
2026-10-24. Other sessions' jobs ran alongside, so the timings were interleaved (pages alternated round by round in one
browser), unleased. Ratios between variants are what to read.

## What limits today's RAM

- **Cost per pass grows with the named cells.** Every leaf has `anchor-name: --c<k>`, and every rendered anchor costs
  ~1.5 µs per layout pass (ENGINE_NOTES 40). Sparse groups keep that to the touched cells. A program that touches the
  heap pays for it: mid-run, `arr_gc.js`'s CPU-only page restyles ~770 RAM tree elements per layout and lays out in
  9.9 ms, against ~10 elements and 3.9 ms for FizzBuzz (`exp/csscpu/stylecount.js`).
- **A miss ends the pass.** The ports read the missing block during the pass's layout; the next pass fills it.
  `deep_recursion.js` ends 961 of its 963 model passes on a miss (`csssim.py`), and every heavy program is mostly
  misses.
- **Bandwidth**: two blocks read and one line written back per pass.
- **Capacity**: 16K words. The read mux (an `if()` over names) and the anchor cost both grow with it.

## Results

### 1. Finding the cell: read ports (`mkread.py`, `readaddr.js`)

One read port at a random address plus one random cell write per trial, forced style + layout, median ms per trial.
The cells are dense (all rendered, no sparse groups), so this is a heavy program's RAM, not FizzBuzz's.

| Variant | 1K | 4K | 16K | 64K |
|---|---|---|---|---|
| `none`: named cells, port reads a fixed name (the floor of today's design) | 0.7 | 2.5 | 10.7 | 87 |
| `ifmux`: named cells, two-level `if()` name mux (today's port) | 0.9 | 2.8 | 14.1 | 87 |
| `keyf`: named cells, paused discrete `<custom-ident>` animation, `animation-delay` = −address | 1.4 | 9.5 | 38.9 | 160 |
| `scope`: a port per group of 256 under `anchor-scope`, then a top port | 1.2 | 7.4 | 19.1 | 129 |
| `grid`: unnamed cells as grid rows, a probe item in row `--addr` | 0.7 | 5.7 | 14.0 | 74, **42/150 wrong** |
| `dec`: unnamed cells; a radix-16 decode tree (memtree's parities, inherited) names the one cell `--rd` | 1.2 | 1.6 | 6.3 | 7.9 |
| `decni`: the same tree, non-inherited properties passed by explicit `inherit` | 0.6 | 1.4 | 2.5 | 6.7 |
| `same`: `decni`, the address arriving **through layout in the same update** (below) | — | 1.7 | 4.4 | 13.7 |

Every variant read exactly, except `grid` at 64K: its rows' heights sum past LayoutUnit's range, so it reads one
low (it needs values < 1,000 even at 16K). `ident()` would replace the mux, but it crashes the renderer inside
`anchor-size()` (survey 09 §2.1, bugs/README). Through a registered `<custom-ident>` (`--n: ident("--c" var(--k))`,
then `anchor-size(var(--n) width)`) it reads 64/64 exactly, behind `--enable-blink-features=CSSIdentFunction`. It is
still `test` in M158, and it would only remove the mux cost: the `ifmux` row minus `none`.

Restyled elements per trial at 16K (`restyles.js`, invalidation trace): `none` / `ifmux` 2.7; `dec` 1,284; `decni`
516; `same` 518; out of ~17,500 elements. **The decode tree restyles the path, not the tree**: an off-path node's
children compute constants and the restyle stops there (one level down with explicit `inherit`, two with
inheritance, as `ComputedStyle::ComputeDifference` predicts: a `kInherited` diff only recalcs children). HISTORY dead
end 35 ("read-decoded anchors: whole trees restyled, 90 ms at 16K") likely pushed the address down unmasked (its code
is gone): an inherited address that every node reads restyles every node, as this probe's first `dec` page did
(36 ms at 4K).

**`same`: the address reaches the tree in the same pass.** The RAM tree is outside the chain, so it can't inherit
the miss address the chain's end computes. Instead, a box at the chain's end (here the harness sizes it) is `address + 1` px wide. Around the
tree, a `position: fixed` size container takes `width: anchor-size(<that box> width)`, and the tree's root reads
`round(100cqw / 1px) − 1`. Layout sizes the container, Blink restyles the tree inside that layout (path only), the
selected leaf takes `--rd`, and a port placed after the tree in tree order reads it. All in one update, exact.

### 2. Reading inside the chain (`mkchain.py`, `chainread.js`, `chainstyles.js`)

K nested levels, each a `position: fixed` size container whose width is the RAM cell chosen by the level above
(`anchor-size()` of a muxed name), read back by the next level as `100cqw`. RAM is a linked list, so level K holds
the cell K dependent reads from the start. One forced update, ms per trial, all exact:

| Cells (named), how a level picks the name | K = 1 | K = 8 | K = 32 | per extra read |
|---|---|---|---|---|
| 256, `if()` mux (64 × … two levels) | 0.2 | 1.1 | 4.4 | ~0.14 ms |
| 4,096, `if()` mux | 1.4 | 10.0 | 52–71 | ~1.6–2.2 ms |
| 4,096, keyframe mux | 8.4 | 39 | 183 | ~5.6 ms |
| 16,384, `if()` mux | 8.8 | 44 | 184 | ~5.6 ms |
| 4,096, **size-query mux** | 0.7 | 1.8 | 4.9 | **~0.13 ms** |
| 16,384, **size-query mux** | 4.0 | 5.5 | 11.4 | **~0.24 ms** |
| 4,096, `ident()` (flag) | 1.1 | — | 4.4 | ~0.11 ms |
| 16,384, `ident()` (flag) | 3.5 | — | 5.4 | ~0.06 ms |

- **Dependent reads within one pass work**: 32 pointer-chasing loads in one style + layout, exact. Nested
  `position: absolute` levels don't work: each level's containing block is the level above, which hides the RAM's
  anchors (fallback 0).
- **The cost is the mux.** The anchors cost once per update (3.5–4 ms at 16K named cells, the K = 1 column), and a
  read after that is cheap if the name is. The `if()` mux pays ~0.3–0.5 µs per cell per read.
- **The size-query mux** needs no flag: the level above is a size container as wide as the address + 1. One rule per
  high digit, `@container (width >= h·64 + 1px) and (width < (h + 1)·64 + 1px) { .lv { --nm: if(<64 low digits>) } }`.
  Only the matching rule's `if()` is evaluated, and the low digit is the level's own `round(100cqw / 1px) − 1`. A
  style query can't do this: the level above would have to publish its result's digits in style, and its result is
  its width, known only after its layout.
- Restyles are linear: ~3 resolves per level per update (96 at K = 32), not K²: each container's layout restyles its
  own subtree once. A real instruction level (~60 declarations, ~340 µs) inside such a container may pay part of that
  again; unmeasured.
- Pitfall: `round(down, 100cqw / 1px)` floors an exact 255 px container to 254 (`100cqw` comes out a hair under). Use
  `round(100cqw / 1px)`.

### 3. Storage checks (`feasible.js`)

- **Two words per leaf**: a `content-visibility: hidden` leaf with `contain-intrinsic-size: auto 1px auto 1px`
  remembers width and height separately (1,048,575 × 777, 12,345 × 1,048,000, 3 × 5 exact). That halves leaves and
  anchors, and a port reads two words (`anchor-size(width)`, `anchor-size(height)`).
- **A scroll offset holds a word**: an `overflow: hidden` scroller with one snap area at `top: v` snaps to it while
  `scroll-snap-type` is on. With snapping off it keeps the offset while the area moves, and through `display: none`
  and back. A scroll timeline reads it back. Exact over 4 writes and holds. No content-visibility and no feedback
  loop, but one scroll container per cell, and a read by address needs a timeline-name mux.

## The catalog

Status: **measured** (here or as cited), **known** (in the repo's notes), **untested**, **dead** (with the reason).

### A. Where a word can live

| # | Store | How | Status | Verdict |
|---|---|---|---|---|
| A1 | Remembered size (today) | `content-visibility: hidden` + `contain-intrinsic-size: auto`; visible for the write | known | keep: free while held, readable by `anchor-size()` |
| A2 | Remembered size, **both axes** | width = word 0, height = word 1 | measured (§3) | adopt with any redesign: half the leaves, two words per port |
| A3 | Remembered size, packed | LayoutUnit is 1/64 px with ~2^25 px range: ~31 bits per axis, so 3 words per leaf with fractional packing | untested | not worth it: `var()` keeps 6 significant digits (ENGINE_NOTES 2) and unpacking costs `calc()`s per read |
| A4 | Transition-latched width or custom property | `transition: X 0s 1e6s` holds; per pass (survey finding 5) | known | dead for bulk RAM: every write restarts a transition, which snapshots every registered property (0.06 µs × ~4,000 per write, bugs/README "Performance") |
| A5 | Scroll offset, snap-written | §3 | measured | a latch primitive without a layout loop (registers, sticky flags); too heavy per cell for 16K |
| A6 | Scroll offset via scroll anchoring | `overflow-anchor` shifts `scrollTop` by the height change above the anchor node: an accumulator, `+= Δ` | untested | interesting as an adder (`+=` without reading); no addressing; suppression rules make it fragile |
| A7 | Scroll offset via clamping | shrinking the content clamps the offset: `min(old, max)` | untested | a min-latch only |
| A8 | Registers (view timelines) as RAM | the cache is already 128 words of registers | known | dead: ~20 µs per register per pass (HISTORY 59) × 16K = 330 ms |
| A9 | Unregistered custom properties on an ancestor of the chain | 16K `--m<k>` inherited by the chain, read by a name mux | untested | dead: nothing writes them (data flows down only), and nothing holds them across passes |
| A10 | Keyframes as storage | `@keyframes` values are static; `var()` in keyframes resolves on the animating element | dead | ROM only (see B6) |
| A11 | CSS counters | an exact int32 adder across elements in tree order (survey 03 §1.9) | known | a prefix-sum unit, not storage: a counter's value isn't held across passes |
| A12 | Write-once bits: lazy `<img>` / `<object>` | an element fetches once when first shown and keeps its natural size (ENGINE_NOTES 53, 61) | untested | write-once memory; rewritable only with WOM codes. A curiosity |
| A13 | Child documents (iframes, SVG `<object>`s) as banks | parent → child through the child's viewport size (its `vw`, media queries); child → parent through its natural size (survey finding 1: across processes, one frame of lag) | measured as a channel (survey 01 §1.8) | an L2 / backing store in other processes: ~2 frames per access, but banks run in parallel and don't cost the page's passes |
| A14 | The server, through `NET` | the gateway holds the words; a word ~280–330 ms on the page, 8 frames, up to 14 words/s with 4 modems (BENCHMARKS §16) | measured (as I/O) | unbounded capacity, ~1,000× slower: swap space, not RAM. Needs the gateway (not on the static deploy) |
| A15 | Compression-dictionary store (paint's) | `Use-As-Dictionary` responses persist across reloads | known (paint) | persistent storage across sessions; seconds of latency |
| A16 | Form state, `:visited`, `<details>`, popovers | persistent, but only the user (or script) changes them; `:visited` can't be read | dead | input devices, not memory |
| A17 | Pixels (filters, canvas-like tricks) | `feDisplacementMap` is a gather, `feComponentTransfer` a table | dead | no path from paint back to style or layout without script |

### B. How a port finds the word at a computed address

| # | Mechanism | Status | Verdict |
|---|---|---|---|
| B1 | `if()` name mux, two levels (today) | measured (§1, §2) | ~0.3–0.5 µs per cell per evaluation: 0.3–3 ms at 4K–16K |
| B1b | **Size-query mux**: the reader's container is as wide as the address; a rule per high digit | measured (§2) | 10–25× cheaper than B1 at 4K–16K; needs the address as a size (a layout before the read), which mid-chain reads have anyway |
| B2 | `ident()` | measured with flag (§1) | the cleanest; test-only in M158, crashes inside `anchor-size()`; works through a registered `<custom-ident>`. Watch it |
| B3 | **Decode tree names the cell** (`--rd`), cells unnamed | measured (§1) | **the scaling win**: path-only restyle, a handful of anchors; 2.5 ms at 16K vs 14.1, 6.7 vs 87 at 64K |
| B4 | Decode tree fed through layout (`same`) | measured (§1) | keeps today's same-pass miss latency; 4.4 ms at 16K, 13.7 at 64K |
| B5 | Grid placement (`grid-row: var(--addr)`) | measured (§1; survey PRIMITIVES finding 4: ~15 µs per extra port) | many cheap ports over a small RAM; O(rows) relayout and LayoutUnit overflow rule it out as the main RAM |
| B6 | Paused discrete keyframe table, `animation-delay` = −index | measured (§1, §2) | works, exact; every change rebuilds the keyframe model (~N keyframes + every registration): 3–4× the `if()` mux. A ROM lookup idea at most |
| B7 | View-timeline-indexed keyframes (address = a subject's position) | untested | no rebuild per change, but the address must be a register: a pass of latency |
| B8 | Hierarchical `anchor-scope` ports | measured (§1) | slower: every group's port pays its own mux each pass |
| B9 | Anchor names by position (ENGINE_NOTES 77: a view timeline animates `anchor-name` by where a box shows) | known | the inverse map (position → name), a frame late; no gain over B3 |
| B10 | Container style queries per digit, selector demux | untested | `style()` gates cost a cascade per block per pass (survey finding 7); B3 does the same with `calc()` |
| B11 | `position-try` fallbacks choosing among N anchors | untested | sequential tries, O(N) layouts: dead |
| B12 | Font / GSUB lookup of an address written as text | known (the font CPU) | ROM only, and a shaping costs ms |

### C. When the read happens (latency, bandwidth)

| # | Idea | Status | Verdict |
|---|---|---|---|
| C1 | **Reads inside the chain** (fixed size-container levels, size-query mux) | measured (§2) | exact; ~0.13 ms per dependent read over 4K named cells, ~0.24 ms over 16K, plus the anchors once per pass. A load that misses the cache could finish inside the pass |
| C2 | **Mid-chain fill stages**: every M levels, a size-container read stage fills the pending miss's block (4 words: one container per word, or two with two-word leaves) | untested | a miss is filled M levels later instead of next pass: a miss-bound program (`deep_recursion`: 961 of 963 passes end on a miss) could run several misses per pass. Cost: a read stage per M levels, ~0.13–0.24 ms each, against ~6 ms of fixed cost per pass saved |
| C3 | The pass pump (D nested remembered-size elements → D + 2 passes per frame) | measured (survey PRIMITIVES finding 1) | not RAM itself, but its finding 2 makes remembered sizes update per pass: writes visible next pass, which a redesign should rely on |
| C4 | More read ports | measured cheap with B5 (~15 µs each) and B3 (one path each) | prefetch two lines ahead, or a whole frame's block per bank |
| C5 | Wider write-back (two lines per pass) | untested | heap-heavy programs evict a dirty line per pass (BENCHMARKS §12): a second write channel set per bank |
| C6 | Write-around for fresh heap lines (no read on allocate) | known lead (HISTORY "allocation loops") | fewer fills for `NEW` / `ALLOC`: a machine change, independent of the RAM's structure |
| C7 | Split RAMs by role: a small anchored stack RAM (C1-readable) and a big unnamed heap RAM (B3/B4) | untested | `deep_recursion`-style programs live in the stack; the heap scales separately |
| C8 | An SVG `<object>` fixpoint loop as an in-frame clock (survey finding 2: 700 lifecycles per frame) | known, untested as a CPU | size queries and anchors refresh per iteration, remembered sizes don't: RAM reads would work, writes wouldn't land |

### D. Far-fetched, for the record

- **The mouse pointer as a read head.** Chrome re-hit-tests after layout, so boxes moving under a resting pointer
  change `:hover`, and `:hover` selects. Needs the user's pointer parked; headless can fake it. A tape machine.
- **Cross-document view transitions** capture snapshots of elements across a navigation: state that survives a page
  load, as images only.
- **SMIL** (`<set begin="…">`) writes attributes on events; script-free, but only user events and its own timing
  drive it (survey finding 12), not the CPU.
- **Flex `order` as a sorter and scroll snap as argmin** (PRIMITIVES §4): associative memory (find the nearest key)
  in layout, with the same readback problem.
- **HTTP cache as RAM**: a URL per address that CSS can select among (no `src()`, ENGINE_NOTES 54: every URL is in
  the CSS), its image's natural size as the value; each URL is fetched once per document (ENGINE_NOTES 61), so it is
  write-once per document again.

## What to build

Two changes, independent, each with a first test.

**1. A RAM whose per-pass cost doesn't grow with its size** (§1):

- Unnamed leaves, two words each (A2): half the leaves, no `anchor-name` on any of them.
- Non-inherited decode trees (`decni`) for the write channels and the read ports. Each port is a read path naming
  one leaf (`--rx<bank>`, `--ry<bank>`), and restyles follow the paths. Today's write trees are inherited and
  restyle two levels off the path (~770 elements per layout in `arr_gc`); explicit `inherit` cut that ~2.5× in the
  probe.
- The miss address through layout (`same`): a box at `.ex` sized by `xb` / `yb`, fixed size containers around the
  bank trees, ports after the trees in tree order. Today's same-pass miss latency stays.
- Keep the sparse groups, the console and the overlays. The compile chain's overlays are anchors named `--c<k>` that
  win by tree order, so an overlay area (code, strings: the HOT blocks) keeps today's mux, and the decode serves the
  rest.

Expected: RAM cost per pass about flat in the cells touched. That's 2.5–4.4 ms instead of 10.7–14 ms with 16K cells
live, and 13.7 instead of 87 at 64K. The heap semi-spaces (3,072 words each) and the stack (7,536) are what GC and
recursive programs run out of; this would let them grow. First test: a CPU-only `arr_gc` page from `gen_css.py` with
the new trees, `make c2-all`, then `ab.js` on `halttime.js` against main.

**2. Misses filled inside the pass** (§2, C2): mid-chain read stages with the size-query mux, over today's named
leaves (the mux needs names; with change 1's unnamed leaves, a stage would decode through `same` instead, or keep
names on the hot half). First test: the model. `csssim.py` with a fill every M levels counts the passes saved per
program (`deep_recursion`, `arr_gc`, FizzBuzz). Then one stage at level 16 on a CPU-only page, `make c2`, and
`halttime.js`.

## What we built (2026-10-24)

Both changes are in `gen_css.py` behind flags; the default page is unchanged. C2 passes 149/149 for each variant
below. Timings are CPU-only pages (`halttime.js`, `runMs`, median ratio to `base` per round), interleaved and
unleased. The 1/2/3-stage run had the machine quiet (load ~1), with tight ranges. An earlier loaded run (load 3–10)
had an A-vs-A control that moved 0.93–1.39.

**`RAMNI=1`: non-inherited write trees.** Each tree node takes its parent's parity by explicit `inherit`. A write
restyles one level off its path instead of two: arr_gc ~790 → ~260 RAM elements per layout. Alone it is worth
little: deep_recursion 0.85–0.89, the rest ~1.0 within the noise. The RAM's restyle was never the big cost; layout
and the registers are.

**`RAMDEC=1`: unnamed leaves, read paths, miss address through layout.** This loses (0.95–1.29). The read paths
put the RAM tree's restyle inside layout. The `.memx` size container is resolved during layout, and its subtree is
restyled there, so arr_gc's layout went 9.8 → 16.7 ms. The probe (§1) had the tree alone. On the page, the tree
sits under a container whose size changes every pass. One more pitfall: `.ab` has to come before the 2²¹-px register
boxes, because after them LayoutUnit saturates and the anchor reads height 0.

**`STAGE=s[,s2…]`: a fill stage at each listed chain level.** A stalled instruction re-executes at the stage with
the missing block named through a size-query mux (`.sr1`/`.sr2`, nested fixed size containers). Each stage has its
own write set for a dirty victim. A block written back earlier in the same pass counts as stale. The model
(`csssim.py MIDS=…`, 180 programs, data misses only) gives these passes per program (geomean, total):

| stages | geomean | total |
|---|---|---|
| 16 | 0.779 | 0.670 |
| 11, 22 | 0.709 | 0.576 |
| 8, 16, 24 | 0.682 | 0.532 |

On the page (all with `RAMNI=1`; ratio of run time to base):

| program | 16 | 11, 22 | 8, 16, 24 |
|---|---|---|---|
| fizzbuzz | 0.899 | 0.803 | 0.797 |
| fib | 0.946 | 0.923 | 0.974 |
| primes | 0.852 | 0.873 | 0.865 |
| array_sort | 0.905 | 0.746 | 0.594 |
| str_table | 0.778 | 0.696 | 0.578 |
| obj_keys | 0.969 | 0.962 | 1.050 |
| deep_recursion | 0.620 | 0.557 | 0.534 |
| closure_gc | 0.796 | 0.837 | 0.954 |
| arr_gc | 0.819 | 0.848 | 0.941 |
| geomean | 0.836 | 0.796 | 0.787 |

Every stage costs each pass. The register subjects (~390 `.sub`) restyle again inside each stage's two containers,
and the CSS grows ~0.9 MB per stage. Passes saved pay for that on the miss-heavy programs (deep_recursion,
array_sort, str_table). On the GC programs, the third stage saves fewer passes than it costs. Without `RAMNI`, one stage
lost on the heavy programs in the loaded run (deep_recursion 1.68 with a 0.95–7.2 range, closure_gc 1.12). The
likely cause is that the stage's write set adds write channels to trees that restyle two levels off every path. This
wasn't re-measured quiet.

Two stages (`STAGE=11,22 RAMNI=1`) is the best balance: no program slower, geomean 0.80.

**The editor page** (`UI=1`, `ui_seq.js`, Run → HALT with the compile included, 6 rounds, quiet). Compile is
1.03× slower with one stage and 1.05× with two (fizzbuzz's `compiledMs`): the compile chain pays for the extra
registers (+32 per stage) every pass. A short program's ~1 s run can't win that back. Long ones do:

| program | base | 16 | 11, 22 |
|---|---|---|---|
| fizzbuzz | 3.78 s | 1.028 | 1.056 |
| array_sort | 3.81 s | 1.010 | 1.047 |
| str_table | 3.19 s | 0.987 | 1.068 |
| deep_recursion | 64.9 s | 0.711 | 0.619 |
| closure_gc | 89.7 s | 0.810 | 0.809 |

Making it the default would trade a few percent on every short program for 20–40% on the long ones.

## Reproducing

```
cd js-minus-js/exp/ram
python3 mkread.py <none|ifmux|keyf|ident|dec|decni|same|scope|grid> <cells> page.html
ROUNDS=5 TRIALS=30 node readaddr.js a.html b.html …     # interleaved, one browser; WRITE=0: reads only
node restyles.js page.html                               # restyled elements per trial
python3 mkchain.py <ifmux|cq|keyf|ident> fixed <cells> <levels> page.html
ROUNDS=3 TRIALS=10 node chainread.js a.html …
node chainstyles.js page.html …                          # resolves per update: linear or K²
node feasible.js                                         # ident (flag), two words per leaf, snap-latch cells
```

`ident` pages need `FLAGS=--enable-blink-features=CSSIdentFunction`, and `mkread.py ident` pages crash the renderer
(the `anchor-size(ident())` crash). `mkchain.py ident` uses the registered-property form.
