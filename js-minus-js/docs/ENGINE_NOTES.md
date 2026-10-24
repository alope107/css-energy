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
   are signed, |v| < 2^19 (`gen_css.py`). *(measured 2026-10-14; probe: `var-6-digits`)*
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

25–33 are what the font CPU relied on (removed; its code last exists at commit `181cbb7`). The readback font
(`mkfont2.py`) still relies on 31.

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

## The network modem (`NET`, `net/server.js`)

50. **A quirks-mode page applies a same-origin stylesheet whatever its Content-Type**: `application/json`,
    `text/plain`, `text/html`, even `image/png`. A standards-mode or XHTML page applies only `text/css`, no
    Content-Type, or `application/x-unknown-content-type`. `X-Content-Type-Options: nosniff` still blocks it.
    (`StyleSheetContents::ParseAuthorStyleSheet`: lax iff quirks mode and CORS-same-origin;
    `CSSStyleSheetResource::CanUseSheet`.) The page is XHTML, which has no quirks mode, so until 2026-10-22 the modem, an
    HTML iframe without a doctype, read the gateway's answers this way (a stylesheet `rx` per load); now the gateway
    writes them into the modem's documents, which saves that request. *(measured 2026-10-19; probe: `quirks-lax-css`)*
51. **Responsive iframes carry a number from a child document to the page**: `frame-sizing: content-height` on the
    iframe, `<meta name="responsive-embedded-sizing">` in an HTML child. Chrome 153 needs
    `--enable-blink-features=ResponsiveIframes` and reads the meta's content as the allowed origins (`*`); 155 has the
    feature on and reads `allow-origins=*`. The modem has both metas; each version ignores the other's. The height is
    recorded at DOMContentLoaded and at load (or by script, `requestResize()`), not as the content changes: the child
    must load again to report again. Each report marks the iframe for layout, changed or not. It works cross-site,
    with the child in its own process. *(measured; probe: `responsive-iframe`)*
52. **The reported height is measured with the viewport the child document started with**, which is the iframe's
    height then (`LocalFrameView::NaturalSizeLayoutScope`, "consistent ICB"): content shorter than that reports the
    viewport, so a reported height never shrinks. The modem reports `100vh + mod(R - 100vh, 4096px)`, which grows the
    iframe by less than 4096 px to the next height that is R mod 4096, and the page reads it mod 4096. A document that
    isn't opted in clears the size (the iframe falls back to 150 px): `/net/reset.html`, past 2^24 px. *(measured)*
53. **An `<object>` or a lazy iframe fetches when first shown, and only then**: under `display: none` neither is
    fetched; showing it fetches; hiding and showing it again reuses the frame and fetches nothing
    (`HTMLPlugInElement::AttachLayoutTree`: "re-use it now. We do not want to reload the frame"); Firefox doesn't re-fetch
    either, WebKit does, and the spec's re-fetch is an open issue (`../../bugs/README.md`). So CSS fires each
    such element's request once. A 404 shows the object's fallback content. An SVG's natural size comes from its
    `width` / `height` attributes (`SVGSVGElement::IntrinsicWidth`), not from CSS. A non-lazy iframe is fetched even
    under `display: none`. Repeatable requests need a document that reloads itself: `<meta http-equiv="refresh"
    content="0">` reloads about 75 times a second beside an idle page. *(measured)*
54. **There is no `src()`: a CSS URL can't be computed**, so every URL the page can request is in its CSS. What CSS
    can choose is which one: `background-image: if(style(--x: v): url(…); …)` requests the chosen URL in each fresh
    document (with `Cache-Control: no-store`), while `@import` and `<link>` are fetched whatever their media.
    *(measured)*
55. **A same-process child gets few loads when the page's frames are heavy, and a cross-site child slows the page's
    frames.** (Measured with the font CPU's height-channel modem, superseded by 56.) Beside the CPU page the modem loaded about 3 times a second in process (the page at 11–13 frames/s,
    0.7–0.8 s per word). Cross-site (the page on 127.0.0.1, the modem on localhost: `net/server.js` rewrites the
    iframe's URL) it loads about 40 times a second in its own process, but the page dropped to 5–6 frames/s; still
    0.5 s per word, about 3 frames. Pacing the modem to 9 loads/s gave 14.5 frames/s but 1.06 s per word; layout
    containment around the iframe changed nothing. *(measured 2026-10-19)*
56. **A same-origin child's fragment scroll moves the page's scroll containers**: an iframe navigated to `x.html#t`
    scrolls its `overflow: hidden` ancestors on the page so that `#t` is in view. With `#t` as wide as the box and after a
    span R px wide, the box's `scrollLeft` is R (larger or smaller than before), and a scroll timeline reads it. This is
    the modem's answer channel: no flag (unlike responsive iframes, 51), 2 ms after the child's load. Facts:
    a cross-origin or `data:` child scrolls nothing; `<meta http-equiv="refresh" content="0">` to the same URL doesn't
    reload (alternate two URLs: 118 loads/s beside an idle page); the box may be `position: fixed; visibility: hidden`;
    `scrollLeft` is exact to 2^25 px, but a scroll timeline's registered integer is off by 2–4 above 2^24 (floats), so
    answers stay below 2^20; the fragment survives a redirect and a form GET (`action="x.html#t"`). From the user's
    `net/xhtml-tests/readback`. *(measured 2026-10-20; `net/probe/probe5.js`)*
57. **A quirks-mode `data:` child reads any CORS-enabled response as CSS**: a cross-origin `<link rel=stylesheet
    crossorigin>` applies whatever its Content-Type (JSON, `text/plain`, `text/html`) if the response has
    `Access-Control-Allow-Origin`; without `crossorigin` only `text/css` or none applies. A `data:` or `srcdoc` child
    can opt in to responsive sizing (51) when the page is http (an `about:blank` page matches no source list), also when
    reached by a form GET; each navigation resets the iframe to 150 px first, so answers below 150 read 150. `data:` URL
    navigations load up to between 2,030 and 2,050 KB. Trap: Chrome's memory cache hands a URL's earlier response to a
    later request in another CORS mode; give each probe its own URL. *(measured 2026-10-20; `net/probe/probe4.js`)*
58. **Several modem children run side by side, paced by the page's frames**: beside the page running a `read()` loop
    (34 frames/s, 4.3 words/s), one more child doing its own round trips ran at 4.0–4.2 words/s and the page's own
    stayed at 4.0–4.2 (8.0–8.2 in all); three more: 3.6 each, 14.3 in all. A word takes about 8 page frames whichever
    child carries it. *(measured 2026-10-21; `net/probe/probe7.js`, the extra children driven by the harness)* Built
    into the page (4 modems, 2 bytes each), a body takes half the time, not a quarter: the 4 modems' reloads cost the
    page a third of its frames (32 → 22 frames/s), and the CPU then works through 8 bytes per word (BENCHMARKS §16).
59. **A box that goes `display: none` keeps its scroll offset and gets it back when it shows again**
    (`PaintLayerScrollableArea`: saved into the element when the box is destroyed, restored when it is made again;
    `paint_layer_scrollable_area.cc` 173 / 219 in 153). A scroll timeline on it then reads the old offset at once. With
    the modems inside `#clk` (hidden by Edit), the last run's answers came back on Run and passed for the first word's
    (the gateway never saw it). Hence the modems' boxes outside `#clk`, never hidden; a hidden *child* (now the iframe's
    clip box, `.nclip`) only leaves its box nothing to scroll, which clamps the offset to 0. *(measured 2026-10-21)*
60. **A transition latch fed by a value that an animation changes didn't hold here**: `--nlive: min(1, var(--rreq));
    transition: --nlive 0s calc((1 - min(1, var(--rreq))) * 1000000s)`, with `--rreq` from a scroll-driven animation on
    the same element or inherited from its parent, followed `--rreq` back to 0 within the frame, where memtree's group
    latch (fed by registers) holds. A held register (`rlive`, zeroed by Edit like the others) latches instead.
    *(observed 2026-10-21, not reduced)*
61. **A document fetches a CSS image URL once**: `CSSImageValue::CacheImage` keeps the image it fetched, and the style
    engine caches image contents by URL per document (`StyleEngine::CacheImageContent`), so an `if()` that comes back to
    a branch it took before requests nothing, `no-store` or not. A request a document sends more than once needs a URL
    that changes: the modem's digit URLs carry a tag that every new word changes (its sequence bit) and the document's
    id. *(Blink source, 153; the modem's tags rely on it)*
62. **A navigation the server holds leaves the old document working**: while an iframe's next document (here its
    `<meta http-equiv="refresh" content="0">`) waits for the response, the old one stays, is laid out on resize and
    sends the requests its CSS chooses; the new one replaces it at commit. 20 s of waiting raised nothing. Each held
    navigation holds one of Chrome's 6 connections per host, so the gateway holds at most 4 per browser.
    *(measured 2026-10-22; `net/server.js`)*
63. **Each same-process child document costs its page two forced style + layout updates**: `Document::FinishedParsing`
    calls `UpdateStyleAndLayoutTree()`, and after the load, once the document lays out with `document.fonts.ready`
    still pending, `FontFaceSetDocument::FireDoneEventIfPossible` (a task posted by `DidLayout`) calls
    `UpdateStyleAndLayout()`. A child's update first updates its owner's document (`Document::UpdateStyleAndLayoutTree`),
    so on the CSS CPU page each is a style pass of the page between frames, 10–13 ms here (traces, the tasks' `posted
    from`: `html_document_parser.cc ScheduleEndIfDelayed`, `font_face_set.cc HandlePendingEventsAndPromisesSoon`). With
    4 modems, one document each per word, that was 8 updates and ~100 ms of the page's main thread per word, a third of
    it. A render-blocking stylesheet arriving after the parse (at once or 15 ms later) didn't skip the first.
    `visibility: hidden` on the iframe skips a third, the load event's (`Document::ImplicitClose` checks
    `View()->IsVisible()`). Hence two answers per document (ARCHITECTURE §3.8). *(measured 2026-10-22)*
64. **A `requestAnimationFrame` loop in the page runs the network programs ~1.5× faster**: `net_long` 6.7–6.9 s with a
    harness's rAF loop, 9.9–11.5 s without (FizzBuzz ~10–20%). In 2.5 s of trace Chrome ran 48 lifecycle updates with
    the loop and 34 without (99–142 `BeginMainFrame`s), for the same style work. The page has no script, so time it
    without one: `net/probe/pagenet.js` had one to count frames until 2026-10-22 (BENCHMARKS §16's earlier times).
    *(measured 2026-10-22)*
75. **Formatted text pasted into a contenteditable keeps its style attributes, and they beat author rules**: VS Code
    pastes `<div style="font-family: …; white-space: pre">` around a `<div>` per line, a web page a `<pre>` with
    highlighting spans, Google Docs `<p>`s in a `<b>`. With the editor's `.ed :not(div, br) { all: unset }` the pasted
    font and white-space still applied (inline style wins over a normal author rule): the line showed one way and the
    probe font read another, and every such paste gave a syntax error. `!important` beats the style attribute; `all`
    leaves `unicode-bidi`, and a `<pre>` (or a div, UA style) isolates: its text is a shaping run of its own, which a
    probe font's sentinel doesn't see. `unicode-bidi: normal !important` with it reads the paste as shown.
    *(measured 2026-10-23; tests/editor_input.js "paste formatted …")*
76. **Replacing many lines of a contenteditable costs one forced style and layout update per line, and positional
    selectors make each restyle all following siblings**: pasting 400 lines over 400 ran ~406 style recalcs, each over
    every remaining line and its `::after` (824, 822, … elements: the `.ed > div:nth-of-type(k)::after` rules), plus
    the probes the `:has(> … > div:nth-of-type(k))` rules hide: 4.3 s, and 24.9 s for 1,600 over 1,600. Rules inside an
    `@container style()` query that is false still do it (Chrome matches their selectors, and :has() still invalidates);
    leaving the probes' contents out (`content-visibility: hidden` while editing) cut a 200-over-200 formatted paste
    from 3.5 s to 1.2 s. *(measured 2026-10-23; BENCHMARKS §18)*
77. **A discrete animation of `anchor-name` on a view timeline names a box by where it shows**: `@keyframes` with
    `anchor-name: --r0`, `--r1`, … over ranges of view progress, run on `animation-timeline: view(block …)`, gives each
    `::before` / `::after` the name of the row it is laid out in, however deep its element is nested, and
    `anchor-size()` reads the animated name (a probe per row). It takes a layout to apply: the names are last frame's.
    A view inset of `calc(100% - X)` cuts the scrollport to a fixed X, so a scroller that grows doesn't move the
    progress of the rows above X. Measured in the editor: a sentinel's box (16px, the probe font's content area at
    16px) starts at its 24px row's top, and progress is `(X - top) / (X + 16)`; except a `::before` in a block that
    holds only inline content, whose progress put it 12px higher (line 0 alone in the editor read as no row) until a
    `display: block` `::after` put the inline content in an anonymous block. Positional selectors can name only an
    element's siblings, and each line a paste adds or removes restyles every one of them (76).
    *(measured 2026-10-23; readback/ui_rb.py; tests/editor_input.js)*
78. **A contenteditable's empty line needs its placeholder `<br>` rendered, and Tab always leaves it**: with
    `br { display: none }` an empty `<div><br></div>` has no caret position, so ArrowUp/Down skip it, a click can't
    land in it, and typing lines with blank ones between lost a blank (`display: contents`, `position: absolute`,
    `float`, `font-size: 0` on the `<br>` either hid it the same way or still broke the line). Rendered, it breaks the
    line, so a sentinel after it starts a second row: the editor's sentinels lead their rows instead. Shift+Enter writes
    `abc<br>def` (no trailing `<br>` once text follows), so a mid-line `<br>` can't be told from a placeholder by a
    selector. Tab: `KeyboardEventManager::DefaultTabEventHandler` moves focus unless the document is in design mode
    (script only); past the last element `FocusController` hands focus to the browser's UI, so the Tab key never
    reaches the editor's InsertTab command. *(measured 2026-10-24; Chromium 153 source; tests/editor_input.js)*
79. **A change an animation makes doesn't start a transition; a container query's does.** A latch held by
    `transition: --v 0s calc((1 - var(--g)) * 1000000s)` never held when `--v`'s change came from an inherited custom
    property that an animation (a view timeline register) drives: `getAnimations()` listed no transition, and the value
    followed at once. With the gate in a rule, `@container style(--g: 1) { .x { --v: …; transition-delay: 0s } }` over
    `--v: -1` and a 1,000,000 s delay, the transition starts and holds the last value (the editor scan's latches work
    this way, through `@container rbscan style(--rbscan: k)`). The REPL's display latches so (ARCHITECTURE §3.10).
    *(observed 2026-10-24, Chromium 153)*
80. **A positioned element outside a `contain: strict` subtree can anchor to an element inside it**: the console box
    (`position: absolute`, containing block the initial one) takes `anchor(--rbed top)` / `anchor-size(--rbed width)` of
    the editor inside `#app` (`contain: strict; will-change: transform`), and follows it. The other way round doesn't
    serve: a reader's anchors must be inside its containing block (the console box holds its leaves and its readers).
    *(observed 2026-10-24, Chromium 153)*
81. **A view timeline's progress counts relative positioning, not transforms** (scroll-animations-1 §3.1: "Transforms
    are ignored, but relative and absolute positioning are accounted for"): a `::before` with
    `animation-timeline: view(block)` in a line div moved down 100px by `position: relative; top: 100px` reads the
    progress of a box 100px lower (0.555 against its row's 0.870); moved by `transform: translateY(100px)` it keeps its
    row's. So the REPL moves its lines down with a transform (ARCHITECTURE §3.10): with `position: relative` the rows'
    names (ENGINE_NOTES 77) followed the lines, the probes read the wrong rows, and the session stopped compiling. The
    sentinels are inline `::before`s, and Chrome takes an inline subject's position to be its containing block's origin
    (the line div's), ignoring its own place and offsets, against the spec (bugs/chrome-view-timeline-inline-relative.html):
    so a row's name is its line div's position, which `position: relative` on the div moves.
    *(measured 2026-10-24, Chromium 153; machine/replui.py)*
82. **A decode tree restyles its paths, not the tree, when the off-path nodes' children come out equal.** Blink
    recalcs only the children of an element whose diff is `kInherited` (`ComputedStyle::ComputeDifference`,
    `ApplyComputedStyleDiff`), and each child's own diff decides whether to go on. With memtree's two parities and the
    address masked by the enable at every level, a read address changing at 16K cells restyled ~1,300 elements per
    update (inherited properties: two levels off the path), ~520 with non-inherited properties taken by explicit
    `inherit` (one level), out of ~17,500. An unmasked inherited address, or any inherited property every node reads,
    restyles every node (likely HISTORY dead end 35). *(measured 2026-10-24; exp/ram §1, restyles.js)*
83. **A paused animation's `animation-delay` picks a keyframe, exactly, in the same style update**: a discrete
    `<custom-ident>` animation, `animation: nm Ns linear paused both; animation-delay: calc(-1s * var(--i) - 0.25s)`,
    names the anchor `anchor-size()` reads. Every change rebuilds the keyframe model, so it costs ~N keyframes per
    change: 3–4× an `if()` over the same names at 4K–16K. *(measured 2026-10-24; exp/ram §1)*
84. **Nested `position: fixed` size containers chain layout → style inside one update**: a level's width is
    `anchor-size()` of a name chosen from the level above's `100cqw`, and 32 dependent reads come out exact in one
    forced update (~3 resolves per level, linear). Nested `position: absolute` levels can't: each level's containing
    block is the one above, and anchors outside it aren't acceptable (fallback). `100cqw / 1px` comes out a hair
    under an exact width: `round(down, …)` floors 255 to 254, so round to nearest. A size query on the level above
    makes a cheap name mux: one `@container (width >= a) and (width < b)` rule per high digit, so only that rule's
    `if()` is evaluated (10–25× cheaper than one two-level `if()` at 4K–16K). *(measured 2026-10-24; exp/ram §2)*
85. **A `content-visibility: hidden` leaf remembers both axes**: `contain-intrinsic-size: auto 1px auto 1px` keeps
    width and height separately (exact up to 2^20 px each), so a RAM leaf can hold two words. *(measured 2026-10-24;
    exp/ram §3, feasible.js)*
86. **A scroll offset is a latch written by snapping**: an `overflow: hidden` scroller with one snap area at `top: v`
    snaps to it while `scroll-snap-type` is on; with snapping off it keeps the offset while the area moves, and through
    `display: none` (59); a scroll timeline reads it. `ident()` (test flag) works in a registered `<custom-ident>`
    (`--n: ident("--c" var(--k))`, then `anchor-size(var(--n) width)`), where `anchor-size(ident(…))` itself crashes
    (bugs/README). *(measured 2026-10-24; exp/ram §3)*
