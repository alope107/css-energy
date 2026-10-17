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

## Open questions and ideas not tried

- **`ERR_FAILED` on a few probes, on Cloudflare only.** Served headers and bytes match the files exactly. Not
  reproduced locally over HTTP, HTTP/2, with 80 ms of added latency, or with all 480 cells written. Suspects:
  HTTP/3 (the host advertises it), or an extension. A failed matching probe drops a pixel from that load's read; the
  stored value is untouched. A `chrome://net-export` capture would settle it.
- **Read retry**: a second set of probes, with fresh URLs, for cells still blank after a few seconds.
- **Staggered reads**: start the probes a row at a time to keep fewer requests in flight.
- **Packing**: `zoom: 17^j` on cell j's probes, so one row reads several cells as one number.
- **A save area for js-minus-js**: read once at boot into machine RAM, write back; the scroll register (48 bits,
  synchronous) as a superblock with a "formatted" flag and an atomic bank switch.
- **Save codes**: copyable text generated from RAM and parsed back by a font, for more than ~500 bytes.
