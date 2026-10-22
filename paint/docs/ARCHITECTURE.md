# Architecture

The canvas keeps no state in the page. Each cell's colour lives in Chrome's compression-dictionary store, a
per-site store the browser keeps on disk for Compression Dictionary Transport (`Use-As-Dictionary`,
`Available-Dictionary`, `Content-Encoding: dcz`). CSS writes it by loading files and reads it by loading probes. The
host only serves static files with fixed headers.

## The store

- A response with `Use-As-Dictionary: match="<URLPattern>"` that is fresh-cacheable becomes a dictionary for later
  requests matching the pattern. Its key is (match pattern, destinations), not its URL: loading another file with the
  same pattern replaces it. That replacement is the write.
- A later request matching the pattern carries `Available-Dictionary: :<sha-256>:`. A `dcz` response starts with a
  36-byte header holding the hash of the dictionary it was compressed with; Chrome decodes it only if that is the
  dictionary it advertised. Otherwise the request fails (`ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER`).
- Limits (Chromium `services/network/shared_dictionary`): `kDictionaryMaxCountPerNetworkContext = 1000` per profile,
  and `cache_max_count_per_site() = cache_max_count_ / 2`, so 500 per top-level site. Every frame under one top-level
  page shares that site's 500.
- Dictionary transport needs a secure context: HTTPS, or `http://localhost`.

## A cell

Cell k owns the path namespace `/c/k/`. `_redirects` maps every cell's URLs to shared files, so the site has 16
dictionaries, 16 probes and one writer page however many cells there are:

```
/c/:k/w     /w        200      the cell's writer
/c/:k/r/:v  /r/:v     200      probes
/c/:k/d/:v  /d/:v     200      dictionaries (written as d/<v>.png?<slot>)
```

`_headers` matches the **request** path, so each cell gets its own pattern from the placeholder:

```
/c/:k/d/*     Use-As-Dictionary: match="/c/:k/r/*"   Cache-Control: public, max-age=31536000   Vary: *
/c/:k/r/*     Content-Encoding: dcz   Cache-Control: no-store   Vary: accept-encoding, available-dictionary
/c/:k/w       Cache-Control: no-cache
```

- `d/v.png` is a valid 1×1 PNG with a unique `tEXt` chunk: valid, because an image load that fails to decode is
  cancelled before Chrome stores the dictionary; unique, because the bytes are the value.
- `r/v.png` is a (v+1)×1 PNG, zstd-compressed against `d/v.png`.
- `Vary: *` on dictionaries keeps Blink's memory cache from serving a reused write URL without a network request.

## Reading (the page)

For each cell the page holds a row of 16 probes, `<i style="content:url(/c/k/r/v.png)">`. Only the probe for the
stored value decodes; a failed probe is 0 px wide. So the row is (value + 1) px wide, and 0 for a cell never written.

```css
.c   { anchor-scope: --rd }
.rd  { position: absolute; display: flex; anchor-name: --rd; opacity: 0 }               /* the probe row */
.v   { position: absolute; width: anchor-size(--rd width); container-type: inline-size } /* the reader   */
.px  { --bv: calc(100cqw / 1px - 1); background: if(style(--bv: 0): var(--p0); …) }       /* --bv: <integer> */
```

The reads must live in the one top-level document. When each cell's own document read its probes, 480 frames put
about 7,700 requests in flight at once, Chrome rejected the excess before sending them, and those cells read blank. A
single document's loader throttles itself.

Each probe URL is fetched once per document, so the page reads each cell once per load, plus one retry.

### Retry

A probe can fail outright, not just answer "no". Cloudflare ends every connection after about 10,000 requests
(HTTP/2: `GOAWAY` with last stream 19999; HTTP/3: a close with `H3_NO_ERROR` and no `GOAWAY`), and a load is about
9,000. When the HTTP/2 `GOAWAY` arrives, Chrome retries the streams the server refused but fails a few hundred
requests it had queued with `ERR_FAILED`, never sent and never retried ([crbug 355006326]; the cause is in
`SpdySession`, `bugs/README.md`). The HTTP/3 close fails everything in flight. Either way about 5–30 cells read
blank on most reloads on the live site; locally, over HTTP/1.1, never.

So a cell still blank after the first pass reads again, with fresh URLs:

```css
.stage > .sig { display: flex; width: 536px }             /* the grid's 528 px + one 8×1 sentinel */
.gd      { flex: 1 1 0; container: s1 / inline-size }      /* 536 px; 528 once /s.png loads */
.gd .gd  { container-name: s2 }                            /* inside it, the same with /s.png?2: 528, then 520 */
@container s1 (width < 532px) { .sig > i.s2 { display: block } }      /* start the second sentinel */
.v   { animation: go-late 0s 90s forwards }                            /* --go: 1 */
@container s2 (width < 524px) { .v { animation: go 0s 3s forwards } }
@container (width: 0px) { .rt { display: if(style(--go: 1): flex; else: none) } }   /* the second row */
.w   { width: max(100cqw, anchor-size(--rt width, 0px)); container-type: inline-size }
```

- The first sentinel `<i style="content:url(/s.png)">` (no-store) comes after every probe in the document, at the
  same priority, so it loads once the first pass has gone out. But a `GOAWAY` re-sends the refused requests after
  it, so the second sentinel, `/s.png?2`, is requested only when the first has loaded, and queues behind them. Three
  seconds after it, `--go` turns 1; if a sentinel fails, 90 s after load.
- Each sentinel narrows its own `.gd` container, which can't depend on its contents, from outside: the `.sig` row
  is fixed width and the sentinel takes 8 px of it. The scale for small screens is on the outer `.sig`, so the
  extra 8 px scale with the grid.
- `.rt` holds 16 probes `/c/k/r/2/<v>.png` (another `_redirects` rule onto `r/<v>.png`, inside the dictionary's
  `match`). Descendants of a `display: none` element get no style, so nothing loads until the row shows.
- `.w`, inside `.v`, is the reader the pixel queries: the wider of the two rows.
- The condition is "first row 0 px wide", so a cell never written always pays its 16 probes twice (7,680 more
  requests for an empty canvas).

[crbug 355006326]: https://issues.chromium.org/issues/355006326

## Painting

The page owns the input and the display; small writer documents do the writes. (Until October 2026 each cell was a
document of its own and painting was a link click that navigated it: `HISTORY.md` §8 says why drags ended that.)

### Input and display

```css
.c                    { --L: -1; transition: --L 0s 1e7s }              /* the colour painted in this page */
.grid:active .c:hover { --L: var(--pal); transition-delay: 0s }
.px { background: if(style(--L: -1): <the colour read>; else: <colour L>) }
```

- Pressing anywhere on the grid makes it `:active`; every cell the pointer enters while it is takes the palette
  colour. A click is a one-cell drag. The colour shows in the frame the pointer reaches the cell, before any write.
- The latch: leaving the cell starts a transition back to -1 with a 1e7 s delay, which holds the colour; the next
  paint of the cell starts one with no delay.
- `.px` shows `--L`, else the colour read, else nothing: a cell never written shows the grid's checkerboard, so it
  can't be mistaken for colour 0.
- The grid is one document because a press is captured by the frame it starts in: when cells were `<object>`
  documents, a drag that began in one never reached the others (`:hover` stayed on the first, in the page too).

### Strokes

Chrome delivers about one pointer position per frame, so a stroke faster than a cell per frame (~1,300 px/s at 60 Hz)
would leave gaps. The page draws the line between consecutive frames' positions instead:

- `.grid` holds the stroke's cell as numbers, `--qr`/`--qc`, and `--qv` = drawing: for the mouse 20 row and 24 column
  rules, `.wrap:active:has(.y5:hover) { --hr: 5 }` (gated by `:active`, so hovering costs nothing; a tapped
  touch handle carries the same classes); for a touch drag the handles' drag, below. `--or`/`--oc` is where a stroke's first segment starts: the cell itself for the mouse, the cell
  the finger came down on for touch.
- `.gw` (`display: contents`, between the grid and the cells) copies them 1 ms late with transitions: at the next
  frame the transition has finished, so `.gw` holds the previous frame's position (`--pr`/`--pc`/`--pv`).
- Each cell paints if it is on the line from the previous position (or the origin, on a stroke's first frame) to the
  current one: one cell per step along the major axis, the nearest, rounding half up (Bresenham's line, as
  arithmetic on the cell's own `--kr`/`--kc`). `tools/e2e.js` checks lines that jump 6 cells a frame cell by cell.
- All of these are registered `inherits: false`, and `.c` takes them with `inherit`: a stroke frame restyles the 480
  `.c` elements and nothing under them.

### Writes

Each cell holds three writer `<object>`s, `/c/k/w`, all hidden until the cell is first painted in this page; a hidden
`<object>` creates no frame and loads nothing, so a page that paints nothing loads no documents. A shown writer is
sized `(22 + L) × (22 + slot)` px, and reads both from its viewport:

```css
:root { --L: calc(100vw / 1px - 22); --s: calc(100vh / 1px - 22) }       /* registered <integer>s */
b     { background: <colour L>; mask-image: if(style(--L: 0): if(style(--s: 0): url(d/0.png?0); …); …) }
```

The relative URL resolves under `/c/k/`, so one 32 KB file serves every cell, and `_headers` makes it cell k's
dictionary. A document fetches each URL once, so writing a colour the cell held earlier needs a URL the writer hasn't
loaded: the slot.

- **The clock.** Each cell has a paused animation of `--C` (seconds). `--W` follows `--L` 50 ms late (a transition
  delay), and the clock runs while they differ, so each change advances it at least 50 ms (measured: 50–150 ms).
  The slot is `floor(C / 40 ms)` mod 64: every change moves to a slot the writer hasn't used, about 1.75 slots per
  change. Within the 50 ms the slot may step twice; each step is a fresh URL of the same colour.
- **Writers.** After 64 slots the next writer takes over (`--wj`), a fresh document with fresh URLs: about 36 changes
  per writer, 110 per cell per page load. After the third, the cell's spinner stays: unsaved until a reload. Every
  shown writer is one of Chrome's ~1,000 frames per page; a writer once shown keeps its frame (hiding an `<object>`
  keeps its document).
- **The gate's form matters.** `animation-play-state: if(style(--L: var(--W)): paused; else: running)` on the
  element whose `--W` transitions failed: Chrome recomputes animation properties from the base style, and a
  transition ending doesn't restyle them, so some clocks ran on forever. The working form computes
  `--d: calc(var(--L) - var(--W))` on a child and tests `style(--d: 0)` on a grandchild, from inherited values.

### Saving indicator

The page draws a spinner (`mix-blend-mode: difference`, visible on every colour) under the writer. The writer's
square is masked by its write: a mask image still loading paints nothing, so the spinner shows through until the
dictionary file has loaded, which is when it registers. Each slot restarts the spinner (`--wp`, the slot's parity
between two identical keyframes); it stops turning after 28 s but stays visible. A reload before it disappears
can lose that paint.

### Touch

A finger drag gets no `:hover` and only a passing `:active`, so touch screens (`@media (pointer: coarse)`) borrow
css-physics's handles (`../../css-physics/docs/ARCHITECTURE.md`, Touch), with a different way to collect them:

```
.wrap                     position: relative; overflow: clip
  .hds                    the handles, one per cell, over the canvas
    .hd > b > em > strong > i (rest area), u (follow area), p > s (publisher)
  .R                      width/height: anchor-size(--drag …); container-type: size
    .Rv                   --tgi, --tdx, --tdy decoded from 100cqw / 100cqh
      .grid > .fo, .gw > .c …
```

- A handle `.hd` is a scroller resting mid-content (3000, 3000). The gesture latches to the handle under the finger;
  its offset from rest is the drag in grid px (Chrome maps it through the page's `scale`), read by the handle's own
  anonymous `scroll()` timelines as `--tx/--ty`. `scroll-axis-lock: none`, `overscroll-behavior: contain`: drawing
  never scrolls the page.
- **Publishing.** While off rest (step keyframes: 0 within 0.6 px of rest) the handle names its publisher `s`
  `anchor-name: --drag`. `s` is `(index + 1) × 8192 + 3000 + tx` px wide and `3000 + ty` px tall, inside a 0×0
  `overflow: clip` box so it doesn't stretch the scroller. `.R`, after the handles in tree order, is sized by
  `anchor-size(--drag)` (3000 × 3000 with no drag), and `.Rv` reads the numbers back from container units. The
  numbers then reach `.grid` and the cells as the mouse's do.
- **Why not sum timelines.** The first build gave `.grid` one additive animation per handle and axis, on timelines
  hoisted with `timeline-scope`, as css-physics does for its ≤ 64 bodies. With 960 of them every layout took ~94 ms
  (mini PC, leased): scoped timelines consumed by animations cost about 0.1 ms each per layout, wherever the
  consumers sit (20 row elements of 48: 75 ms; `timeline-scope: all`: 24 ms). Named or anonymous timelines consumed
  inside their own scroller cost nothing measurable. A stroke lays out every frame (the follow area, the follower,
  new writers), so the page ran at ~8 fps.
- **Finger down**: the follower `.fo`, a snap container whose snap area sits at the drag, re-snaps after every layout
  except while a scroll gesture is active (`touch-snap-defer` in `../../engine/`), so `--held` is "`.fo` lags".
  A stroke needs `--held` and a handle off rest.
- **Back to rest without `--held`** (which lives in `.Rv`, after the handles): a handle snaps to an area around its
  current offset (`u`, which follows the offset) until the offset has been still for 100 ms (`--txd`, a copy 100 ms
  late), then to its rest area (`i`). During a gesture Chrome defers that re-snap to the gesture's end, so a pause
  mid-stroke moves nothing; a lift while moving keeps the handle where it is (no snap motion) until it has been
  still. A handle back at rest unnames its publisher, so the jump to rest is never drawn. A fling stops within
  40 px (the follow area's margin).
- The finger's cell, `start row + round(tdy / 22)` and `start column + round(tdx / 22)`, is the stroke position; the
  start cell is the origin, since the first scroll update comes only past the touch slop, often a few cells on.
- A stroke trails the finger by the touch slop (~15 px in desktop Chromium's emulation, ~8 dp on Android): about a
  cell at phone scale, in the stroke's first direction. Taps paint through the hover rules (the handles carry the
  cells' row and column classes).

## URLs

Every page URL is extensionless (`/c/k/w`). Cloudflare redirects `*.html` to the extensionless path; a redirect
inside a 200 rewrite would leave the `/c/<k>/` namespace. Files keep `.html` on disk; Cloudflare and `serve.js` serve
`w.html` at `/w`.

## Capacity

500 entries per site × log₂K bits per entry, with K probes to read a cell (each probe is an equality test, so
reading can't be cheaper than K). The host's file limit caps K at half its file count (Cloudflare Workers: 20,000
files per version on the free plan).

| K | Per cell | 500 cells | Probes per read |
|---|---|---|---|
| 16 (this canvas) | 4 bits | 250 B | 16 |
| 256 | 8 bits | 500 B | 256 |
| 4096 | 12 bits | 750 B | 4,096 |

## Feeding a CSS machine

The read already ends as a registered `<integer>` (`--bv`), so a machine's read port can take it the way
js-minus-js reads anchor sizes: nest the port under the reader, or give it `anchor-size()` of the probe row.

- Values arrive asynchronously, over seconds: wait on a ready flag (row width > 0). Format every cell once on first
  run so that 0 always means "not loaded yet".
- Read once per page load into machine RAM, and write back. In-page writes from a register: a child with
  `mask-image: if(style(--w: 0): url(…/d/0.png); …)` under a latched parent, limited to one fetch per URL per
  document. More writes need fresh URLs (the cells' slots: a clock that moves on every change) or fresh documents
  (the cells' writers, three per cell).
