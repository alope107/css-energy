# Engine notes: Chrome, Blink and HarfBuzz behaviour this project depends on

Observed on headless Chromium 153, Linux, `--no-sandbox --disable-gpu`; some may be bugs. Code and docs cite these
**by number**: never renumber. `make engine-check` (repo root, `../engine/README.md`) re-checks the notes marked
*(probe: `id`)*; run it after a Chrome upgrade. *(measured)*: measured when found. *(unverified here)*: from earlier
chats.

## CSS values and custom properties

1. **`@container style()` never matches a calc()-computed `<integer>` ≥ 256** (a literal 256 matches). Keep dispatch
   values (mode, token, variant id, lexer class) below 256; split larger ids. *(probe: `style-int-256`)*
2. **A calc()-computed registered `<integer>` crossing `var()` keeps 6 significant digits**: 1048575 serializes as
   `1.04858e+06`, reads back in `calc()` as 1048580, and a plain `--y: var(--x)` into another registered `<integer>`
   is invalid at computed-value time (initial value, silently). Literals keep all digits. So words crossing `var()`
   are signed, |v| < 2^19 (`gen_fvm4.py`). *(measured 2026-10-14; probe: `var-6-digits`)*
3. **Registered integers are stored as floats.** The DSL keeps |value| < 2^24 (`dsl.py`).
4. **Every registered property costs time on every animated element, used or not.** Temps share a pool of names
   (`ccpage5.py`); the page has 4,229 `@property` rules (2026-10-18).
5. **Inherited properties that change every frame restyle the whole subtree.** Driver state is `inherits: false`. An
   earlier page with inherited routing properties: 167 ms per pass instead of 14. *(unverified here)*
6. **Identical sibling elements share computed style**, so replicated "hardware" must stay textually identical.
   *(unverified here)*
7. **Rules selected by container query only cost where they match**, so per-(mode, token) variants win: a level
   evaluates only its own. *(measured)* But each rule still costs a test on every element it's tested against (a
   false `style(--x: v)` 0.8 µs, `style(--x)` 0.5 µs, a range query 1.7 µs: css-physics `docs/BENCHMARKS.md` §2),
   and every token level tests every variant rule (BENCHMARKS §4c). `and` stops at the first false test (left to
   right; nested `@container` innermost first): put the most selective test first. Over-specialising to 46 MB of CSS
   was slower.
8. **The `font` shorthand resets `font-variation-settings`** when declared after it. *(probe: `font-resets-fvs`)*

## Animations and timelines

9. **`animation-play-state` is read from the base style**: a pause driven by an animated flag is ignored.
   *(probe: `play-state-base`, the literal reading: an element's own animated flag in `animation-play-state:
   if(style(…))`)*
10. **An animation created paused doesn't reliably take its timeline's value.** Sources keep running; the chain is
    shown and hidden instead (`display: if(style(--ccgo: 1): …)`).
11. **A paused animation keeps its value after its timeline is detached.**
12. **An animation on an inactive timeline costs nothing**; an active pair costs every frame.
13. **An animation on every level of a deep chain restyled the chain per timeline update, ~3 ms per level.**
    *(measured)* Animate a few sources (per line, per 32 tokens) and let levels inherit.
14. **View-timeline registers update every layout pass; remembered sizes once per frame** (`memtree.py`).
15. **Chrome re-runs style and layout within a frame while view timelines are stale**: later passes already show
    next frame's counter. Gate per-frame updates on a freshness flag (`--rbfresh`, `ui_rb.py`).
16. **When nothing changes, Blink stops re-running layout within the frame.** Saturate counters (`min(K, k + 1)`)
    so frames settle.
17. **A hidden element has no registers** (inactive animations, stale inherited values). Give it base values (a line
    past the text must read as spaces, `ccpage5.py`).
18. **A time-driven scan skips columns when frames are slow.** Lock scans to frames.

## Layout, DOM and parsing

19. **The HTML parser stops nesting at 512 elements; XHTML doesn't** (`display: contents` chains work ≥ 4,000 deep).
    *(probe: `html-nesting-512`)*
20. **`display: contents` levels avoid deep layout recursion**; `contain: strict` keeps the chain out of the CPU's
    per-frame layout.
21. **With a shared anchor name, `anchor-size()` reads the last element in tree order.** Compiler overlays override
    RAM leaves this way; only for cells the program never writes. *(probe: `anchor-last`)*
22. **A RAM leaf is a `content-visibility: hidden` element whose remembered width is the value.** Off-path decode
    nodes computing constants took style + layout from 70 to ~20 ms per pass, but only on passes where the channels
    don't change (see 41). *(measured)*
23. **A 0 s transition writes and a 1,000,000 s delay holds**: the "transition latch" of readback cells and RAM
    groups. It kept up to 200 burst writes without frames between. *(unverified here)*
24. **Run state is read with sibling selectors** (`#run:checked ~ …`), not `:has()`; reason unrecorded, likely
    `:has()` invalidation over 10k elements.

## HarfBuzz and fonts

25. **One Lookup can be referenced many times from the LookupList**, so one shaping runs S cycles. fontTools can't
    express it, hence `otl.py`.
26. **The OTS sanitizer rejects more than 16,384 subtables.** uharfbuzz (no sanitizer) loads such a font but never
    runs the lookups past the cap: at 531 per cycle × S = 32 the export lookup was dropped and every register read
    0, silently (2026-10-17). Keep S × subtables per cycle ≤ 16,384.
27. **Contexts are capped at 64 glyphs, and a match consumes its whole input**, hence one lookup per broadcast. Two
    rules of one lookup with overlapping input spans can't both apply (the later-starting is skipped): two temp loads
    in one micro-cycle (`T3 := MDR`, `T1 := IMM`) or the two sign flags need a lookup each. One expression's digits
    can share a subtable, since each digit's span ends before the next digit's source (`cpu4.merge_digits`).
28. **HarfBuzz cost ≈ rules tried × context walk distance.** Make state glyphs GDEF marks and use mark-filtering sets
    so each lookup sees only its cells (`cpugen.py`).
29. **Positions must line up exactly**: HarfBuzz is 16.16 fixed point, Chrome positions in whole device pixels. One
    font unit = one device pixel, no glyph ≥ 32,768 device px, ratio found by resolution media queries (`zoomfix.py`).
30. **Shaping runs across span boundaries within a line**, so a span's width can depend on its neighbours; the
    state readback relies on it.
31. **A variable axis can switch lookup sets via GSUB FeatureVariations, and a GPOS kern can cancel a sentinel's
    width.** The readback font uses both (`mkfont2.py`).
32. **Not in any shipping browser**: the HarfBuzz WASM shaper; multicore (one document's style, layout and shaping
    share a thread; cross-origin iframes get processes, but the parent can't read their results). *(multicore: measured by css-physics,
    `docs/BENCHMARKS.md` §5: cross-site iframes get their own processes, and the only script-free channel is the
    iframe's size, parent to child; the WASM shaper: unverified)*
33. **avar2 can compute arbitrary two-input lookup tables** (Chrome 148+; Fontations had a perf bug ~axes³). Unused.
    *(unverified here)*
34. **A size container restyles its dependent subtree inside layout, every pass its size is dirty.** Trace category
    `disabled-by-default-devtools.timeline.invalidationTracking` shows `StyleResolver::ResolveStyle` instants: on the
    CPU page 98% were inside `Layout` (~1,300 per pass, under the readback readers) against ~48 in
    `Document::recalcStyle`. Keep what sits under a size container tiny. *(measured 2026-10-13)*
35. **A view-timeline subject may be absolutely positioned in its scroller** (`top` from container units); the
    timeline is active with no in-flow content under `overflow: hidden`. The registers work this way.
36. **`will-change: transform` on a large static pane stops root-layer re-recording** (~7 ms per frame from the CPU's
    per-pass invalidations; `#app` has its own layer). *(measured)*
37. **More than two issues per frame run on stale state**: 3 or 4 gave duplicate steps (1,555 and 3,323 instead of
    1,329) and garbage; 2 issues (3 passes per frame) are exact. The limit's cause wasn't found. *(measured)*
38. **Blink doesn't always run the settle pass**: the CPU-only page mostly ran 2 passes per frame, the full page
    always 3, both correct. The trigger is `#cpu`'s `ScrollTimeline` style invalidation after the second shaping.
    Unexplained: 1,536 extra active view-timeline animations *removed* the third pass on the CPU-only page at no
    cost; a time-driven animation changed nothing (2026-10-13).
39. **The trace window must sit inside the run.** `trace.js` `RUN=1` traces from `RUNWAIT` ms after Run (default 8 s);
    FizzBuzz halts ~10.8 s after Run, and idle frames past HALT flatter everything. Use `RUNWAIT=3500`, 4 s.
40. **Every rendered anchor costs ~1.5 µs per layout pass**, read or not (Blink merges children's anchors into the
    containing block's anchor query). 32K anchored cells: 272 ms per frame, 137 ms without the unused ones' names.
    *(measured 2026-10-13)*
41. **A changing inherited custom property restyles the whole subtree below, every time**; redeclaring it constant
    one level down doesn't stop that. A read block pushed down the RAM trees each pass resolved ~38,000 elements per
    pass at 16K (90 ms). Keep per-pass state `inherits: false` and off the ancestors of big subtrees. *(measured;
    qualifies 22)*
42. **A `display: none` subtree costs nothing per pass**, and a transition-latched property can show it for good on
    first write (`memtree.py` groups). Hidden elements aren't anchors, so `anchor-size(--n width, <fallback>)` reads
    the fallback. Traps: the latch delay also delays a static first 0 → 1 (always-on elements need
    `transition: none`), and `display: if(style(--x: 1))` doesn't match 2, so clamp summed flags.
    *(measured; probe: `anchor-hidden`)*
43. **An advance is at most 32,767 font units**, so a 4-hex-digit span carries 15 bits; 16-bit addresses would need a
    second span.
44. **Enter in text directly inside a contenteditable host nests every later line** (`a<div>b</div>` →
    `a<div><br/><div>b</div></div>`; no CSS changed it). Hence an all-div initial program.
45. **Select-all then Delete, Backspace or Cut empties the host**, and new text goes straight into it. No guard
    element prevented that without breaking something else.
46. **Copying from a contenteditable writes every matched author rule into `style=""`**, and pasting such lines
    nests them. With no rule matching the line divs, pasted lines merge flat (except into an empty line).
    `plaintext-only` makes Enter insert `\n` instead of a div.
47. **Selected text is painted at GPOS-adjusted positions**: while the scan ran, a selection over line 0 painted
    shifted or not at all in 14–19 of ~105 frames. Hence scanning only after Run. *(measured)*
48. **With `white-space: pre`, pasted plain text and Shift+Enter insert `\n` inside the line**; otherwise paste
    splits into divs and Shift+Enter inserts `<br>`. `white-space-collapse: preserve-spaces` is unsupported in 153.
    Hence `nowrap` and `&nbsp;`.
49. **An inline `div` is a separate shaping run** (UA `unicode-bidi: isolate`), which the scan's GSUB chain can't
    cross. `unicode-bidi: normal` (or `all: unset`) fixes it.
