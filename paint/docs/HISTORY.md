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

## 2. Compression dictionaries (2026-10-12)

`Use-As-Dictionary` turned out to be a store that CSS can write (load a file) and read (a probe compressed against
one dictionary decodes only if that dictionary is current). Found along the way:

- A dictionary must be fresh-cacheable: `no-store`, `no-cache` and `max-age=0` never register.
- Dictionaries loaded as images must be valid images: random bytes lost about 75% of writes, because the decoder
  cancels the load before Chrome stores it.
- Reusing a write URL in the same tab failed every third round until dictionaries got `Vary: *` (Blink's memory
  cache served the old response without reaching the network).
- Which loads register: `mask-image`, `filter: url()`, `@font-face`, `@import`, lazy `<img>`, prefetch, preload. Not
  `background-image` or `cursor`. Iframe and object documents don't register either.
- 500 entries per top-level site (512 written, 12 lost), from Chromium's constants; frames of other origins share
  the parent site's 500.
- First demo: 16×16 binary pixels, 8 paints per pixel per load.

## 3. More bits per entry (2026-10-12)

- K dictionaries per cell give log₂K bits; a read is K probes, because each probe is an equality test.
- File count went from one file per (cell, value) to 2K for any number of cells: the cell number moved into the
  probe's query string, and one `_redirects` rule maps every cell's dictionary URL to a shared file. URLPattern
  gotcha: `match="/r/*?k-*"` never matched, because `*?` is an optional wildcard; `"/r/*.png?k-*"` works.
- K = 16, 256 and 4096 all read back with 0 errors, including after a browser restart.
- Canvas v1: 24×20, 16 colours, one document, 6 paints per cell per load (write URLs carry a slot number). The
  paint colour is latched with `transition: --c 0s 1e9s`. An `if()` picking the write URL had to sit on a child:
  on the same element it saw the pre-transition value, so a palette change rewrote painted cells.

## 4. Unlimited writes (2026-10-13 → 10-17)

- **Cells as documents.** Each cell became a same-origin iframe whose relative URLs resolve under `/c/<k>/`; painting
  navigates it to a new document, which has a fresh fetch memo. Back and Forward became undo and redo.
- **Reads failed inside 480 frames.** With each cell document reading its own probes, a reload lost 12–200 cells.
  A net log showed the requests created and never sent: about 7,700 in flight at once, past Chrome's limit, with
  no retry. Reads moved to the top-level page, which throttles its own loads. The cell learnt its value through
  its height instead.
- **Undo didn't persist.** Back restored the picture, but storage kept the undone colour: the server saw no request
  at all. History traversal serves every CSS-initiated fetch from cache (mask-image, `@import`, fonts, prefetch,
  even with `no-store` documents), and a cached response doesn't register. Only `<link rel=compression-dictionary>`
  went to the network. Its `media` attribute is ignored (both links of a pair loaded), so it couldn't be made
  conditional on the value passed in by height.
- **A page per value.** Each cell instead starts on the page for its value, so the link can be unconditional. First
  try: 16 hidden `loading=lazy` iframes per cell. Loading stalled after 59 cells: every iframe takes one of Chrome's
  ~1,000 frames per page, even hidden and never loaded. Hidden `<object>`s take none, so the cells use those.
- **The link alone was too slow.** It loads when the network is idle: ~150 ms normally, ~30 s while the page is
  still probing. A paint followed by a quick reload was lost. Painted pages now write both ways.
- A test once expected one undo step too many: repainting a cell its current colour is a same-URL navigation, which
  replaces the history entry.

## 5. Cloudflare (2026-10-14 → 10-17)

- GitHub Pages can't set headers, so it can't host this.
- Cloudflare's own Shared dictionaries feature strips dictionary headers when "disabled" and passes them through on
  "passthrough". `selftest/` checks a deployment for exactly the four things the canvas needs; it passed on the
  user's deployment.
- Pages redirects `*.html` to extensionless paths, which inside a rewrite would leave a cell's namespace: every URL
  became extensionless. Pages joins a header set by two `_headers` rules with `, `, so rules must not overlap.
- On the deployment, the console shows `ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER` for every probe that answers
  "no", as designed.

## 6. Missing pixels on the live site (2026-10-18)

Reloads of the Workers deployment showed a few blank cells that the next reload found again: the `ERR_FAILED`
probes noted on Pages. Measured in headless Chromium 153 against `paint.auberon.workers.dev`, 480 cells written, a
net log per run:

- **Cloudflare ends every connection after about 10,000 requests.** HTTP/2 sessions got `GOAWAY(NO_ERROR,
  last_stream_id=19999)` after 10,011–10,039 streams; the HTTP/3 session got `CONNECTION_CLOSE` (application,
  `H3_NO_ERROR`, no HTTP/3 `GOAWAY`) after 10,514. A load is about 9,000 requests (7,680 probes, 480 cell pages,
  960 writes), so a connection kept across reloads hits the limit in most loads.
- **HTTP/2: Chrome fails part of its queue.** At the `GOAWAY` it had ~50–80 streams active and hundreds queued on
  `SETTINGS_MAX_CONCURRENT_STREAMS` (100). It retried ~650 refused requests, but 200–500 failed with `ERR_FAILED`
  within 50 ms, never sent: a race in `SpdySession` (`bugs/README.md`; reported as crbug 355006326). The lost probes
  come in a run, so 5–31 adjacent cells read blank per load.
- **HTTP/3: the close fails everything in flight** (495 requests, `ERR_CONNECTION_CLOSED`), and Chrome then marks
  HTTP/3 broken for the origin and uses HTTP/2.
- Local tests never saw it: `serve.js` speaks HTTP/1.1 (six connections, no limit). `serve.js --goaway 10000`
  reproduces it over HTTP/2: 32 blank cells in one load, the same `ERR_FAILED` signature.
- Nothing on the page can keep a connection under 10,000 requests or stop Chrome's race, and fewer probes per cell
  isn't possible (each probe is one equality test). So a cell still blank after the first pass reads again, with
  fresh URLs (`ARCHITECTURE.md#retry`).
- **When to retry.** A fixed delay is either late or doubles a slow read. A sentinel image after the grid loads once
  the first pass has gone out, but after a `GOAWAY` the re-sent requests queue behind it: with one sentinel the retry
  started 6–11 s early and sent 2,300–3,900 retry probes for cells still loading. A second sentinel, requested only
  when the first has loaded, queues behind them: it finished within 50 ms of the last first-pass probe, and the
  retry sent exactly 16 probes per lost cell.
- Retry results, local HTTP/2 with `--goaway 10000` (`tools/goaway.js`), 11 loads after the first: the first pass
  lost 0–32 cells per load (152 in all); the retry sent 16 probes per lost cell and every load ended with all 480
  cells right. `make test` passes unchanged. Not yet measured on Cloudflare.

## Open questions and ideas not tried

- **Fewer requests per load** would make the connection limit fall in fewer loads: the cell pages' own writes on
  load (480 mask-images now, 480 links when idle) only repeat the stored value. The start page needs the link (undo
  back to it re-registers), not the mask-image.
- **Staggered reads**: start the probes a row at a time to keep fewer requests in flight.
- **Packing**: `zoom: 17^j` on cell j's probes, so one row reads several cells as one number.
- **A save area for js-minus-js**: read once at boot into machine RAM, write back; the scroll register (48 bits,
  synchronous) as a superblock with a "formatted" flag and an atomic bank switch.
- **Save codes**: copyable text generated from RAM and parsed back by a font, for more than ~500 bytes.
