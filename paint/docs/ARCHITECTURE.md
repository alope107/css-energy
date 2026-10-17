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
dictionaries, 16 probes and 17 pages however many cells there are:

```
/c/:k/x     /cell     200      the page of a cell never written
/c/:k/p/:v  /p/:v     200      the page of a cell holding colour v
/c/:k/r/:v  /r/:v     200      probes
/c/:k/d/:v  /d/:v     200      dictionaries
```

`_headers` matches the **request** path, so each cell gets its own pattern from the placeholder:

```
/c/:k/d/*     Use-As-Dictionary: match="/c/:k/r/*"   Cache-Control: public, max-age=31536000   Vary: *
/c/:k/r/*     Content-Encoding: dcz   Cache-Control: no-store   Vary: accept-encoding, available-dictionary
/c/:k/p/*     Cache-Control: no-store
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

Each probe URL is fetched once per document, so the page reads each cell once per load.

## Cells and writing

Each cell holds 17 `<object>`s, all `display: none` except one: `p/<v>` for the value just read, or `x` while the
row is 0 px wide. A hidden `<object>` creates no frame and loads nothing. (An `<iframe>` would not do: each one takes
one of Chrome's ~1,000 frames per page even when hidden and `loading=lazy`, and loading stalled after 59 cells.)

```css
.c object { display: none }
@container (width: 0px) { .c object.x  { display: block } }
@container (width: 6px) { .c object.f5 { display: block } }       /* colour 5 */
```

The cell documents are tiny pages with 16 links, `href="<v>"` (or `p/<v>` from `x`), one per colour. The palette
lives in the parent; it reaches every cell through the `<object>`'s width, `calc(23px + var(--pal) * 1px)`, clipped
by the 22 px cell, and the cell shows only the link for that colour: `@media (width: 28px) { a.a5 { display: block } }`.

A click follows the link: the cell navigates to `p/<u>`, a new document, which writes u twice:

- `mask-image: url(../d/<u>.png)` on a 1 px element: registers at once.
- `<link rel=compression-dictionary href="../d/<u>.png">`: fetched when the network is idle. It is the only write
  that reaches the network when the page is restored by Back/Forward, where every CSS-initiated fetch comes from
  cache and a cached response registers nothing.

Each navigation is a new document with a fresh fetch memo, so writes are unlimited. The cell's starting page writes
its own value again on every load; harmless, the same value.

## Undo

Every paint is a history entry of the cell's `<object>`. Back reloads the previous `p/<v>` (no-store), whose
`<link rel=compression-dictionary>` registers v again; Forward does the same for the later one. Because each cell
starts on its value's page, undo works back to the colour it had when the page loaded.

- Repainting a cell its current colour is a same-URL navigation, which replaces the entry: not an undo step.
- A cell that was blank at load starts on `x`, which writes nothing: undoing its first paint shows blank but keeps
  the colour stored. Writing "blank" from `x` would erase real data whenever a read failed, because "never written"
  and "read failed" look the same (no probe decodes).

## URLs

Every page URL is extensionless (`/c/k/x`, `/c/k/p/5`). Cloudflare Pages 308-redirects `*.html` to the extensionless
path; a redirect inside a 200 rewrite would leave the `/c/<k>/` namespace. Files keep `.html` on disk; Pages and
`serve.js` serve `p/5.html` at `/p/5`.

## Capacity

500 entries per site × log₂K bits per entry, with K probes to read a cell (each probe is an equality test, so
reading can't be cheaper than K). The host's file limit caps K at half its file count (Cloudflare Pages: 20,000
files free, 100,000 paid).

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
  document; unlimited writes need a document per write, as the cells do.
