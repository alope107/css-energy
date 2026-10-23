# History

How the project got here, and what failed on the way. Every test ran in headless Chromium (141, then 153) in a
cloud sandbox, against local servers that apply the same headers a static host would.

## 1. Looking for state that survives a reload (2026-10-12)

The question: can pure CSS keep state across a page reload? Channels tried:

| Channel | Survives reload | Verdict |
|---|---|---|
| Root scroll position, written by scroll snap, read by scroll-driven animations | yes | 48 bits (2²⁴ per axis, exact), per history entry. `overflow-anchor: none` is essential: otherwise Chrome restores relative to an anchor element. A counter demo worked, including a browser restart with session restore. |
| Nested scrollers, iframe scroll, iframe URLs | no | reset on reload (subframes restore only on Back/Forward) |
| Form control state | no | restored on Back/Forward only |
| Fractional or negative (RTL) scroll | — | whole pixels, same 2²⁴ range: no extra bits |
| HTTP cache as a timing channel (probe image latched at 30 ms) | yes | 1 bit per URL, write-once, and it depends on latency. Rejected as too flaky. |
| History entries + cross-document view transitions | partly | 48 bits per entry carried between pages, but nothing script-free can traverse history; a stack, not RAM |
| Geolocation permission (`<geolocation>`, `:granted`) | yes | 1 bit, set by the user |

## 2–3. Compression dictionaries, more bits per entry (2026-10-12)

`Use-As-Dictionary` is a store CSS can write (load a file) and read (a probe compressed against one dictionary decodes
only if it is current). The registration rules in `CLAUDE.md` came from failures here: `no-store`/`no-cache`/
`max-age=0` never register; random-byte image dictionaries lost ~75% of writes (the decoder cancels the load); reused
write URLs failed every third round until `Vary: *`.

- K dictionaries per cell give log₂K bits; a read is K probes (each is an equality test). K = 16, 256 and 4096 all read
  back with 0 errors, including after a browser restart.
- One file per (cell, value) became 2K files for any number of cells: one `_redirects` rule maps every cell onto shared
  files. URLPattern `match="/r/*?k-*"` never matched (`*?` is an optional wildcard).
- Canvas v1 (one document, 6 paints per cell per load): an `if()` picking the write URL had to sit on a child of the
  latched colour; on the same element it saw the pre-transition value, so a palette change rewrote painted cells.

## 4. Unlimited writes (2026-10-13 → 10-17)

- **Cells as documents:** painting navigates the cell's frame to a new document, which has a fresh fetch memo; Back
  and Forward became undo and redo.
- **Reads inside 480 frames failed:** ~7,700 requests in flight, past Chrome's limit, never sent or retried. Reads
  moved to the top-level page.
- **Undo didn't persist:** history traversal serves every CSS-initiated fetch from cache, and a cached response
  doesn't register. Only `<link rel=compression-dictionary>` reaches the network, and its `media` is ignored, so it
  couldn't be made conditional: each cell starts on the page for its value instead.
- **16 hidden lazy iframes per cell stalled after 59 cells** (~1,000 frames per page, hidden or not). Hidden
  `<object>`s take none.
- **The link alone was too slow** (it loads when the network is idle, ~30 s while probing), so a paint followed by a
  quick reload was lost. Painted pages write both ways.

## 5. Cloudflare (2026-10-14 → 10-17)

GitHub Pages can't set headers, so it can't host this. Cloudflare's Shared dictionaries setting strips dictionary
headers unless set to passthrough; `selftest/` checks a deployment for the four things the canvas needs. `*.html`
redirects and joined `_headers` values forced extensionless URLs and non-overlapping rules.

## 6. Missing pixels on the live site (2026-10-18)

Reloads of the Workers deployment showed a few blank cells that the next reload found again. Net logs (headless
Chromium 153, 480 cells written):

- **Cloudflare ends every connection after about 10,000 requests**: HTTP/2 `GOAWAY(NO_ERROR, last_stream_id=19999)`
  after 10,011–10,039 streams; HTTP/3 `CONNECTION_CLOSE` (`H3_NO_ERROR`, no `GOAWAY`) after 10,514. A load is about
  9,000 requests, so a connection kept across reloads hits the limit in most loads.
- **HTTP/2:** with ~50–80 streams active and hundreds queued, Chrome retried ~650 refused requests but failed 200–500
  with `ERR_FAILED`, never sent (a `SpdySession` race, `bugs/README.md`). The lost probes come in a run: 5–31 adjacent
  cells blank. **HTTP/3:** the close fails everything in flight, then Chrome marks HTTP/3 broken for the origin.
- Local tests never saw it (`serve.js` was HTTP/1.1); `serve.js --goaway 10000` reproduces it over HTTP/2.
- Nothing on the page can keep a connection under 10,000 requests, and fewer probes per cell isn't possible, so a cell
  still blank after the first pass reads again (`ARCHITECTURE.md#retry`).
- **When to retry:** a fixed delay is either late or doubles a slow read. One sentinel image after the grid started
  the retry 6–11 s early (re-sent requests queue behind it), sending 2,300–3,900 needless probes. A second sentinel,
  requested only once the first has loaded, finished within 50 ms of the last first-pass probe, and the retry sent
  exactly 16 probes per lost cell.
- Results: local HTTP/2 `--goaway 10000`, 11 loads: 0–32 cells lost per first pass, all 480 right after the retry.
  Workers preview, 5 loads: 0–32 lost, all right after the retry, ~30 s per load.

## 7. Staged reads: built, tested, not adopted (2026-10-18)

An `<img>` probe (no `alt`) is 0×0 while pending, Chrome's 16×16 broken-image box once it fails, and its decoded size
on a hit (`../survey/PRIMITIVES.md`, finding 6), so CSS can see a probe finish. The read became staged: colour 1 (the
default brush) first, the other 15 only on a miss, a retry per cell as soon as its 16 probes all missed. It passed `make
test` and `make test-goaway` (and `GOAWAY=2000`, 5 of 5 loads); the design is kept as a patch,
`../survey/exp/patches/paint-staged-reads.patch` (`build.py`, `tools/goaway.js`, `docs/ARCHITECTURE.md`, against
`59187f4`; the labelled `build.py` since needs it re-applied by hand).

- **`<img>` fetches under `display: none`**: the first build sent all three stages for every cell (15,360 probes).
  `loading=lazy` holds a hidden stage back.
- **A lost request can hang, not fail**: under `serve.js --goaway 2000`, 30–60 cells per load had stage-2 probes sent
  but never answered nor failed, their `<img>` pending for good, so completion never came and nothing retried. The
  two-sentinel trigger came back as a second path: any cell unread some seconds after the second sentinel.
- **The sentinel no longer queues behind every probe**: stage 2 is requested as stage 1 answers, partly after the
  sentinel. At 3 s, `goaway.js` loads re-read 200–260 cells whose stage 2 was still in flight (3,000–4,000 needless
  probes); at 8 s, only the lost cells (16 probes each).
- **Result**: fewer requests where cells hold colour 1 (7,690 vs 10,240 probes with a third of the cells colour 1; about
  6% fewer on a random canvas), never more; but one more round trip for every other cell and a later retry for hung
  probes: on `goaway.js`'s random canvas, loads took 26–33 s against 20–25 s. A cell never written still pays 32.
- **Not adopted**: for this canvas, fewer requests don't pay for slower loads. It may when js-minus-js persists memory
  here (a save area read once at boot: many cells, a likely value per cell), so the patch stays.

## 8. Drag to paint, instant colour, a visible blank (2026-10-22)

The asks: see a paint at once (with a saving indicator), tell a blank cell from colour 0, and paint lines by
dragging, with a mouse and a finger. Headless Chromium 153.

- **A drag can't cross cell documents.** A press is captured by the frame it starts in: pressing in one cell's
  `<object>` and moving over others kept `:hover` (and `:active`) on the first cell, in its document and in the page,
  and the release over another cell clicked nothing. So input moved to the page: `.grid:active .c:hover` latches the
  palette colour into the cell (a transition with a 1e7 s delay holds it). The colour shows in the next frame; the
  old canvas showed it only when the cell's new document arrived, after a round trip (much longer while the page was
  still probing).
- **Writes needed a new channel.** The page can't navigate a cell's document without a click, and re-showing a
  hidden `<object>` keeps its document (no reload, no fresh fetches), so the cell documents went. A writer document
  per cell, shown on the first paint, reads (colour, slot) from its size and writes `d/<colour>.png?<slot>`; a
  per-cell clock gives every change a new slot (`ARCHITECTURE.md`, Writes). Cost: about 110 changes per cell per page
  load (three writers); a writer's 32 KB of CSS is parsed once per painted cell.
- **The clock's gate.** `animation-play-state: if(style(--L: var(--W)): …)` on the element whose `--W` transitions
  left some clocks running forever after the transition ended (animation properties come from the base style and
  aren't recomputed then). Testing `--d = L - W` on a grandchild works: 40 changes, one cell, the clock moved 50–150 ms
  each and never in between.
- **Lost: Back/Forward as undo.** Undo was each cell document's own history. With writes coming from the page there
  are no history entries, and keeping click-paints as navigations beside drags didn't hold up: the page's latched
  colour sits over a cell whose document Back restores, so the display would disagree with the store. Not replaced.
- **Saving indicator.** A mask image still loading paints nothing, so the writer's square, masked by its write,
  covers the page's spinner exactly when the write has loaded. A global "saving" indicator isn't possible: the page
  can't see into the writers.
- **Blank.** The read already tells "never written" (0 px row) from colour 0, so no palette colour was given up: a
  blank cell shows the grid's checkerboard. A read that failed looks the same until the retry.
- **Touch.** css-physics's handles (one scroller per cell, a follower for "finger down"). The first build left
  handles off rest: the follower sat outside `.grid`, so it never saw the non-inherited `--tdx` and `--held` never
  dropped. Then it was correct but ran at ~8 fps: summing 960 additive animations on `timeline-scope`d timelines
  (as css-physics does for ≤ 64 bodies) made every layout cost ~94 ms (leased, mini PC). Bisected with a forced
  layout per variant: no consumers 3.7 ms, consumers inside their own scroller 3.2 ms, 20 row-level sums of 48
  75 ms, `timeline-scope: all` 24 ms, half the consumers 38.5 ms. So the dragged handle publishes instead: an anchor
  whose size encodes (cell, drag), read by `anchor-size()` on a container around the canvas
  (`ARCHITECTURE.md`, Touch). That moved `--held` after the handles in tree order, out of their reach, so a handle
  now returns to rest after 100 ms without movement, a re-snap Chrome defers to the gesture's end.
  `tools/touch.js`: drags, a quick drag lifted while moving, a back-and-forth, a fast diagonal, a tap; strokes trail
  the finger by the touch slop, about a cell at phone scale.
- **Fast strokes left gaps.** About one pointer position arrives per frame, so a stroke faster than a cell per frame
  painted every other cell. The page now keeps the last frame's position (a 1 ms transition) and paints the line to
  the current one. A half-cell distance test made slope-1/2 segments two cells thick at ties; one cell per step along
  the major axis (Bresenham) draws thin lines. Touch strokes started late: the first scroll update comes past the
  slop, so the first segment starts at the cell the finger came down on.
- **"Huge hunks" at fast turns** (the user, 2026-10-23). The previous point was a transition 1 ms late; Chrome
  starts a transition only at a later frame, so with the pointer moving every frame it was replaced before it ever
  finished and stayed at the stroke's start: each frame drew a line from there. Headless tests with a move every two
  frames never saw it; headed Chromium under Xvfb with a move every 4 ms did. Now two latches swap every 10 ms
  (`ARCHITECTURE.md`, Strokes), after three traps: an `if()` on an animated, inherited value in `transition-delay`
  is never recomputed; a held transition carries on if the target doesn't change; a style query on the clock
  restyled the whole grid (100–700 ms frames). The line math moved from 480 cells to 20 rows, and a cell's first
  writer now loads after the mouse is up (documents loading mid-stroke made 100–500 ms frames; passing "drawing"
  down into every cell for that cost more, 40–80 ms recalcs, so it is a `.wrap:active` selector). Testing with moves
  sent through CDP unacknowledged (one per 4 ms, coalesced per frame as a real mouse's are) then showed most of a
  fast stroke missing, intermittently: each cell decided `--on` and used it in its own `transition-delay`, which was
  sometimes stale; the latch moved to a child, `.l`. The first frames of a stroke, before a latch has held a point
  of it, start from the pressed cell (`:active`).
- **Touch was never smooth.** The ~3 ms reported above was a forced layout; a real drag, timed later, ran at 8–12 fps:
  a full re-layerization of 966 composited layers (480 handles) every frame (`ARCHITECTURE.md`, Touch). Not fixed.
- **Load got lighter:** no cell documents at load (they were 480 documents, 480 mask-image writes and 480
  `<link>` writes per load, the first "open question" below), and the page shrank from 1.36 MB to 1.14 MB including
  the touch handles (0.97 MB once the handles publish instead of being summed).

## Open questions and ideas not tried

- **Undo** without history entries: one level per cell is cheap (latch the previous colour); more needs per-cell
  value stacks.
- **Slop compensation for touch**: the stroke trails the finger by the touch slop; the first movement's direction,
  latched, would let the page add it back.
- **Staggered reads**: start the probes a row at a time to keep fewer requests in flight.
- **Packing**: `zoom: 17^j` on cell j's probes, so one row reads several cells as one number.
- **A save area for js-minus-js** (`../COMPARISON.md`), with the scroll register (48 bits, synchronous) as a superblock
  holding a "formatted" flag and an atomic bank switch.
- **Save codes**: copyable text generated from RAM and parsed back by a font, for more than ~500 bytes.
