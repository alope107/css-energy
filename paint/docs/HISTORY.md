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

## 7. Staged reads (2026-10-18)

An `<img>` probe (no `alt`) is 0×0 while pending, Chrome's 16×16 broken-image box once it fails, and its decoded size
on a hit (`../survey/PRIMITIVES.md`, finding 6), so CSS can see a probe finish. The read became staged: colour 1 (the
default brush) first, the other 15 only on a miss, a retry per cell as soon as its 16 probes all missed.

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

## Open questions and ideas not tried

- **Fewer requests per load** would make the connection limit fall in fewer loads: the cell pages' own writes on
  load (480 mask-images now, 480 links when idle) only repeat the stored value. The start page needs the link (undo
  back to it re-registers), not the mask-image.
- **Staggered reads**: start the probes a row at a time to keep fewer requests in flight.
- **Packing**: `zoom: 17^j` on cell j's probes, so one row reads several cells as one number.
- **A save area for js-minus-js** (`../COMPARISON.md`), with the scroll register (48 bits, synchronous) as a superblock
  holding a "formatted" flag and an atomic bank switch.
- **Save codes**: copyable text generated from RAM and parsed back by a font, for more than ~500 bytes.
