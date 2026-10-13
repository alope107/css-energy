# Engine notes: Chrome, Blink and HarfBuzz behaviour this project depends on

These are observed facts, found the hard way and mostly not written down anywhere else. Each one names the file
that relies on it or records it.

- **Tested on**: Chromium 153.0.8010.0, headless, Linux, `--no-sandbox --disable-gpu`. Treat every entry as
  "true there".
- **Re-check after a Chrome upgrade.** Several of these may be bugs, not specified behaviour.
- **Evidence**: entries marked *(measured)* were measured when they were found; numbers for code that still exists are in [BENCHMARKS.md](BENCHMARKS.md), and the rest are in [HISTORY.md](HISTORY.md). The others were
  seen in tests or probes.

## CSS values and custom properties

1. **`@container style()` never matches a calc()-computed `<integer>` of 256 or more.** So anything dispatched by
   style query (parser mode, token code, variant id, lexer class) must stay below 256. Split larger ids into
   small fields. (`compiler/ccpage3.py`, now archived; probes in `archive/spikes/scratch/t*.js`.)
2. **A registered `<integer>` that crosses `var()` keeps only 6 significant digits.** 1048575 came back as
   1048580. Keep 20-bit words signed (|v| < 2^19) in every property that crosses a `var()`.
   (`machine/gen_fvm4.py`, "20-bit machine words are kept SIGNED".)
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
   - Each container rule still costs roughly 1.6–4 µs per element it's tested against.
   - Over-specialising to 46 MB of CSS was slower (`archive/results/compiler/cc3_*.json`).
8. **The CSS `font` shorthand resets `font-variation-settings`** when it's declared after it. (Related chat.)

## Animations and timelines

9. **`animation-play-state` is read from the base style.** A pause driven by an animated flag is ignored
   (`compiler/ccpage5.py`; probes `archive/readback/tl*.js`).
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
    `display: contents` levels work to at least 4,000 deep in XHTML.
20. **`display: contents` levels avoid deep layout recursion.** `contain: strict` on the chain keeps its layout
    out of the CPU's per-frame layout (`ccpage5.py`).
21. **When several elements share an anchor name, `anchor-size()` reads the last one in tree order.** The
    compiler's overlays override RAM leaves this way. Only use it for cells the program never writes.
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
    all under the 74 readback readers (`container-type: inline-size | size`, width from `anchor-size()`), while
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
