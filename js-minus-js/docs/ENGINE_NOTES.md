# Engine notes: Chrome, Blink and HarfBuzz behaviour this project depends on

These are observed facts, found the hard way and mostly not written down anywhere else. Each one names the file
that relies on it or records it.

- **Tested on**: Chromium 153 headless on Linux (153.0.8010.0 from `@sparticuz/chromium`, and 153.0.8010.12 Chrome
  for Testing in the devcontainer), `--no-sandbox --disable-gpu`. Treat every entry as "true there".
- **Re-check after a Chrome upgrade.** Several of these may be bugs, not specified behaviour. `make engine-check` at the
  repo root re-checks the entries marked *(probe: `id`)* on minimal pages (`engine/check.js`, `engine/README.md`).
- **Evidence**: entries marked *(measured)* were measured when they were found; numbers for code that still exists are in [BENCHMARKS.md](BENCHMARKS.md), and the rest are in [HISTORY.md](HISTORY.md). The others were
  seen in tests or probes.
- **`archive/` paths** other than `archive/results/` name code removed on 2026-10-15. It is still in git at commit
  `91d73bc`; `archive/README.md` says how to restore it.

## CSS values and custom properties

1. **`@container style()` never matches a calc()-computed `<integer>` of 256 or more.** So anything dispatched by
   style query (parser mode, token code, variant id, lexer class) must stay below 256. Split larger ids into
   small fields. (`compiler/ccpage3.py`, now archived; probes in `archive/spikes/scratch/t*.js`.) *(probe: `style-int-256`)*
2. **A registered `<integer>` that crosses `var()` keeps only 6 significant digits.** 1048575 came back as
   1048580. Keep 20-bit words signed (|v| < 2^19) in every property that crosses a `var()`.
   (`machine/gen_fvm4.py`, "20-bit machine words are kept SIGNED".)
   - Precisely: it is a *calc()-computed* value that serializes with 6 significant digits (`1.04858e+06`). Inside
     `calc()` that reads back as 1048580. A literal `--x: 1048575` keeps all 7 digits.
   - A plain `--y: var(--x)` of such a value into another registered `<integer>` is invalid at computed-value time:
     `1.04858e+06` is not an integer token, so `--y` silently takes its initial value. Another reason to stay below 10⁶.
   - *(measured 2026-10-14, Chromium 153; probe: `var-6-digits`)*
3. **Registered integers are stored as floats.** The DSL keeps |value| < 2^24 (`compiler/dsl.py`).
4. **Every registered property costs time on every animated element, even where it's unused.** Keep the number
   of `@property` declarations small:
   - temps share a pool of names across parser variants (`ccpage5.py`);
   - the current page has about 3,800 `@property` rules.
5. **Inherited properties that change every frame restyle the whole subtree that inherits them.**
   - Per-frame driver state must be `inherits: false` (`readback/ui_rb.py`).
   - The wall clock animates only `#clk` (`gen_vm.py` lineage).
   - A related chat found writes restyling the entire 7,168-element page with `inherits: true` routing
     properties: 167 ms per pass instead of 14 ms. *(measured, related chat)*
6. **Identical sibling elements share computed style**, so replicated "hardware" must stay textually identical
   to benefit. (Related chat.)
7. **Rules selected by container query only cost where they match.** That makes specialising code per
   (mode, token) a big win: a level evaluates only its own variant. *(measured)*
   - Each container rule still costs time on every element it's tested against. An earlier, undated measurement
     here gave roughly 1.6–4 µs. css-physics measured Chromium 153 on 2026-10-17 on the Ubuntu mini PC (its
     `docs/BENCHMARKS.md` §2): a false `style(--x: v)` costs 0.8 µs per rule, `style(--x)` without a value 0.5 µs,
     a range query such as `style(--x > 5)` 1.7 µs.
   - `and` is evaluated left to right and stops at the first false test; nested `@container` rules evaluate the
     innermost query first (same source). Put the test that rejects most variants first.
   - Over-specialising to 46 MB of CSS was slower (`archive/results/compiler/cc3_*.json`).
   - In the compile chain this is a cost per variant: every token level (400) tests every variant rule. 40 extra
     never-matching variant rules (+13%) slowed L3 by 1.6–4.3%, about 13 ms per pass at 0.8 µs per test; merging the
     variants of a mode that have identical CSS into one rule, `style(--vh: m) and (style(--tcq: a) or …)`, made it
     about 3% faster (302 variants in 168 rules). *(measured 2026-10-17, BENCHMARKS.md §4c)*
8. **The CSS `font` shorthand resets `font-variation-settings`** when it's declared after it. (Related chat.) *(probe: `font-resets-fvs`)*

## Animations and timelines

9. **`animation-play-state` is read from the base style.** A pause driven by an animated flag is ignored
   (`compiler/ccpage5.py`; probes `archive/readback/tl*.js`). *(probe: `play-state-base`, the literal reading: an
   element's own animated flag in `animation-play-state: if(style(…))`)*
10. **An animation created paused doesn't reliably take its timeline's value.** So the compiler's source
    animations keep running, and the chain is hidden and shown instead (`display: if(style(--ccgo: 1): …)`).
11. **A paused animation keeps its value after its timeline is detached.**
12. **An animation on an inactive timeline costs nothing.** An active timeline-plus-animation pair costs time
    every frame.
13. **An animation on every level of a deep chain made every timeline update restyle the chain, about 3 ms per
    level.** *(measured)* Animate on a few source elements instead (one per line, one per 32 tokens) and let
    the levels read by inheritance (`ccpage5.py`).
14. **View-timeline registers update every layout pass. Remembered sizes update only once per frame.** That is
    why the old pure-CSS VM did one instruction per pass and needed K write channels per frame
    (`archive/machine/gen_vm.py`, `machine/memtree.py`).
15. **Chrome re-runs style and layout within one frame while view timelines are stale.** In the later passes, a
    counter register already shows next frame's value. Gate per-frame updates on a freshness flag (`--rbfresh`,
    `readback/ui_rb.py`).
16. **When nothing changes, Blink stops re-running layout within the frame.** Make counters saturate
    (`min(K, k + 1)`) so a frame can settle.
17. **A hidden element has no registers, so its animations are inactive and it inherits stale values.** Give
    such elements base values. For example, a line past the end of the text must read as spaces
    (`ccpage5.py`).
18. **A time-driven scan skips columns when frames are slow.** Lock scans to frames (`readback/ui_rb.py`).

## Layout, DOM and parsing

19. **The HTML parser stops nesting at 512 elements. XHTML doesn't**, so the pages are XHTML. Chains of
    `display: contents` levels work to at least 4,000 deep in XHTML. *(probe: `html-nesting-512`)*
20. **`display: contents` levels avoid deep layout recursion.** `contain: strict` on the chain keeps its layout
    out of the CPU's per-frame layout (`ccpage5.py`).
21. **When several elements share an anchor name, `anchor-size()` reads the last one in tree order.** The
    compiler's overlays override RAM leaves this way. Only use it for cells the program never writes. *(probe:
    `anchor-last`)*
22. **A RAM leaf is a `content-visibility: hidden` element whose remembered width is the stored value.** Writing
    makes it visible with the new width. A decode tree whose off-path nodes compute constants stops restyling
    one level below them: style plus layout per pass went from 70 ms to about 20 ms. *(measured;
    `machine/memtree.py`)*
23. **A 0 s transition writes and a 1,000,000 s transition delay holds.** This "transition latch" is how the
    readback latches keep one character each. A related chat found it keeps up to 200 burst writes with no
    frames in between.
24. **Run state is read with sibling selectors** (`#run:checked ~ …`, with the checkbox as the first child of
    body), not `:has()`. Keep it that way. The original reason isn't recorded, but `:has()` invalidation over a
    10k-element page is the likely cost.

## HarfBuzz and fonts

25. **One Lookup can be referenced many times from the LookupList (aliasing),** so one shaping runs S CPU
    cycles. fontTools' feature compiler can't express this, hence the hand-written GSUB assembler
    `machine/otl.py`.
26. **The OTS sanitizer rejects more than 16,384 subtables,** which caps the aliased step count per font
    (`archive/spikes/first_deliverable/vmfont.py`).
27. **Contexts are capped at 64 glyphs, and a match consumes its whole input sequence**, hence one lookup per
    broadcast (`machine/cpu4.py`).
28. **HarfBuzz's cost is roughly the rules tried times the context walk distance.** Make every state glyph a GDEF
    mark and use mark-filtering sets so each lookup sees only the cells it needs (`machine/cpugen.py`).
    *(per-lookup timing scripts: `archive/machine/`, see `archive/README.md`)*
29. **Glyph positions must line up exactly.** HarfBuzz positions are 16.16 fixed point and Chrome positions glyphs
    in whole device pixels. One font unit must be exactly one device pixel, no glyph may be 32,768 device px or
    wider, and the page finds the device-pixel ratio with resolution media queries (`machine/zoomfix.py`).
30. **Shaping runs across span boundaries within one line**, so a span's width can depend on its neighbours. The
    CPU's state readback (span widths of one shaped line) relies on this.
31. **A variable axis can switch lookup sets through GSUB FeatureVariations, and a GPOS pair kern can cancel a
    sentinel's width.** The readback font is built on both (`readback/mkfont2.py`).
32. **Not available in any shipping browser:**
    - The HarfBuzz WebAssembly shaper.
    - Multicore: within one document, style, layout and shaping run on one thread. Cross-origin iframes get their
      own processes, but the parent can't read their results.

    (Related chats.)
33. **avar2 can compute arbitrary two-input lookup tables.** It shipped in Chrome 148, and Chrome's Rust font
    library (Fontations) had a performance bug that scaled roughly as axes³. A related chat found this; it isn't
    used here yet.
34. **A size container restyles its dependent subtree inside layout, every pass its size is dirty.** With the trace
    category `disabled-by-default-devtools.timeline.invalidationTracking`, `StyleResolver::ResolveStyle` instants
    show where style resolutions happen: on the CPU page 98% of them were inside `Layout`, about 1,300 per pass,
    all under the readback readers (74 then, 76 now) (`container-type: inline-size | size`, width from `anchor-size()`), while
    `Document::recalcStyle` resolved only about 48 elements (`#cpu` and its ancestors). Keep what sits under a
    size container tiny (`machine/gen_fvm4.py`: one scroller, one or two subjects). *(measured, 2026-10-13)*
35. **A view-timeline subject may be absolutely positioned inside its scroller** with `top` from container units;
    the timeline is active with no in-flow content and no scrollable overflow (`overflow: hidden` suffices). The
    registers of `gen_fvm4.py` work this way. *(measured)*
36. **`will-change: transform` on a large static pane keeps the root layer from re-recording it.** The CPU's
    per-pass invalidations (hidden state text, status counters, console cells) made Blink re-record the root
    layer, about 7 ms per frame with the editor and notes in it; `#app` on its own layer removed that.
    *(measured: FizzBuzz 9.3–9.7 → 8.5–8.6 s after Run)*
37. **More than two issues per frame run on stale state.** With `--issue=3` or `4` the CPU executed duplicate
    steps (1,555 and 3,323 instead of 1,329) and the output was garbage; with 2 issues (3 passes per frame) it is
    exact. The third pass propagates the second shaping's registers; what limits the number of useful passes was
    not found. *(measured)*
38. **Blink does not always run the settle pass.** The same CPU page without the editor and compile chain ran
    2 passes per frame in most frames (66 ms), the full page always 3 (125 ms); both are correct. In both the
    trigger of the third pass is the `ScrollTimeline` style invalidation of `#cpu` after the second shaping.
    Not understood: on the CPU-only page a time-driven infinite animation changed nothing (2.5 passes per frame
    either way), and 1,536 extra active view-timeline animations *removed* the third pass (2.00 per frame) at no
    cost in frame time (`scratchpad` experiment `xp_regs`, 2026-10-13).
39. **The trace window must sit inside the run.** `trace.js` with `RUN=1` starts tracing `RUNWAIT` ms after Run
    (default 8 s); once FizzBuzz halts at about 8.5 s, that window shows idle frames (shaping 17 ms per frame
    instead of 34) and flatters every number. Use `RUNWAIT=3500` with a 4 s trace.
40. **Every rendered anchor costs about 1.5 µs per layout pass**, whether or not anything reads it: Blink merges the
    anchors of every child into the containing block's anchor query each time the block lays out. A CPU-only page with
    32K anchored RAM cells spent 272 ms per frame against 137 ms with the unused cells' `anchor-name` removed.
    *(measured, 2026-10-13)*
41. **An inherited custom property that changes restyles the whole subtree below it, every time.** Redeclaring it as a
    constant one level down does not stop the cascade: with a read block pushed down the RAM decode trees every pass,
    `Document::recalcStyle` resolved about 38,000 elements per pass at 16K cells (90 ms). The write channels only
    change on write passes, which is why the trees looked cheap. Keep per-pass state `inherits: false`, and keep
    anything that changes per pass out of the ancestors of large subtrees. *(measured; supersedes the "restyling stops
    one level below" claim in note 22, which holds only for passes where the channel registers don't change)*
42. **A `display: none` subtree costs nothing per pass** (no style, layout or anchors), and a transition-latched custom
    property can show it for good once a write reaches it (`machine/memtree.py` groups: `--live` with a 0 s transition
    and a 1,000,000 s delay, as the readback latches). Elements in a hidden subtree have no anchors, so
    `anchor-size(--name width, <fallback>)` reads them as the fallback. Two things bit: the latch's delayed transition
    also delays a *first* 0 → 1 from a static declaration (give always-on elements `transition: none`), and
    `display: if(style(--x: 1))` matches only 1, so a flag that can sum to 2 must be clamped. *(measured: sparse RAM, HISTORY phase 10;
    probe: `anchor-hidden`)*
43. **The top hex digit of a readback span is limited by the glyph advance**: an advance is at most 32,767 font units,
    so a 4-digit span (weights 1, 16, 256, 4096) carries 15 bits. 16-bit addresses would need a second span per
    register (as T1 / T2 have).
44. **Enter in text that sits directly in a contenteditable host nests every later line.** With blocks after the caret,
    Chrome's paragraph split treats the host as the enclosing block. It appends one new div to the host and moves all
    later siblings into it: `a<div>b</div>` becomes `a<div><br/><div>b</div></div>`. No CSS on the host or the lines
    changed this (block, flex, grid, flow-root, list-item). Enter at the start of that line puts the new empty div
    *before* the bare text. So the editor's initial program is all divs (`readback/ui_rb.py`, `tests/editor_input.js`).
45. **Select-all, then Delete, Backspace or Cut, empties the host.** Text typed next goes straight into the host
    (`a<div>b</div>`). Select-all and then typing keeps the first div. In a random-edit fuzz (60 sequences of 30 edits),
    no guard element kept the host from emptying without breaking something else: a trailing `user-select: none`
    block, `contenteditable="false"`, or a trailing `<br>`.
46. **Copying from a contenteditable writes every matched author rule into `style=""` on the copied elements.** With
    `#ed * { all: unset }` that was about 300 properties per line. Pasting those lines nests them inside the line at the
    caret. With no author rule matching the line divs, Chrome merges pasted lines flat, except when pasting into an
    empty line (`<div><br></div>`), which still nests. `contenteditable="plaintext-only"` makes paste plain, but Enter
    then inserts `\n` instead of a div, and the readback needs an element per line.
47. **Selected text is painted with the GPOS-adjusted positions.** While the scan ran, line 0's leading sentinel took
    a width and a kern pulled the next glyph back over it. A selection covering line 0 then painted its text shifted,
    or not at all, in 14–19 of about 105 frames. The trailing sentinels of the other lines only moved the end of the
    highlight. The scan now runs only after Run. *(measured with a screencast, `tests/editor_input.js`)*
48. **Where newlines are preserved (`white-space: pre`), Chrome pastes plain text with its `\n`s inside the line at the
    caret,** and Shift+Enter inserts `\n`. Elsewhere it splits pasted plain text into one div per line, and Shift+Enter
    inserts `<br>`. `white-space-collapse: preserve-spaces` would keep spaces and drop newlines, but Chromium 153 doesn't
    support it. So the editor uses `nowrap`, and spaces that would collapse are `&nbsp;`.
49. **An inline `div` is a separate shaping run.** The UA stylesheet gives `div` `unicode-bidi: isolate`, so a div
    displayed inline is shaped on its own, and the scan's GSUB chain can't carry a character across it to the line's
    sentinel. `unicode-bidi: normal` (or `all: unset`) puts it back in the line's run (`readback/ui_rb.py`).
