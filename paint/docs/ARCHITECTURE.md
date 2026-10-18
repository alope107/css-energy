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
- `r/v.png` is a (v+17)×1 PNG, zstd-compressed against `d/v.png` (wider than a failed probe's 16 px box, below).
- `Vary: *` on dictionaries keeps Blink's memory cache from serving a reused write URL without a network request.

## Reading (the page)

A probe is an `<img src=/c/k/r/v.png>` (no `alt`), and it has three sizes: 0×0 while pending, Chrome's 16×16
broken-image box once it fails (another value's dictionary, a cell never written, a lost request), and (v+17)×1 once
it decodes. Probes stack vertically, so a stack's width is its widest probe (v+17 if one hit, 16 if all that finished
missed) and its height counts the finished ones (16 per miss, 1 per hit). So CSS knows when a probe has *finished*,
not only when it hit, and reads in stages:

1. **Stage 1:** one probe for colour 1, the default brush (the likeliest painted colour).
2. **Stage 2:** the other 15 probes, shown only once stage 1 missed.
3. **Retry:** 16 probes with fresh URLs, shown once stage 2 has finished with every probe missed (below).

```css
.c   { anchor-scope: --s1, --s2, --rt }
.s1  { position: absolute; anchor-name: --s1 }                                      /* stage 1: one <img> */
.v1  { position: absolute; width: anchor-size(--s1 width); container-type: inline-size }
.s2  { display: none; anchor-name: --s2 }                                            /* stage 2: 15 <img loading=lazy> */
@container (width: 16px) { .s2 { display: block } }                                  /* stage 1 missed */
.v2  { width: max(100cqw, anchor-size(--s2 width, 0px)); height: anchor-size(--s2 height, 0px); container-type: size }
.w   { width: max(100cqw, anchor-size(--rt width, 0px)); container-type: inline-size }   /* the read */
.px  { --bv: calc(100cqw / 1px - 17); background: if(style(--bv: 0): var(--p0); …) }       /* --bv: <integer> */
```

- An `<img>` fetches even under `display: none`; `loading=lazy` holds a hidden stage back (it never intersects the
  viewport), so stages 2 and 3 are lazy and stage 1 isn't.
- `.w` is (value + 17) px wide, or under 17 px for a cell never written; the pixel and the `<object>`s query it.
- Requests per cell: 1 for a cell holding colour 1, 16 for another colour, 32 for a cell never written (1 + 15 + 16,
  as before). For 480 cells, a third colour 1, a third other colours, a third blank: 7,690 probes against 10,240.
  The cost is one more round trip for the cells that aren't colour 1.

The reads must live in the one top-level document. When each cell's own document read its probes, 480 frames put
about 7,700 requests in flight at once, Chrome rejected the excess before sending them, and those cells read blank. A
single document's loader throttles itself.

Each probe URL is fetched once per document, so the page reads each cell once per load, plus one retry.

### Retry

A probe can fail outright, not just answer "no". Cloudflare ends every connection after about 10,000 requests
(HTTP/2: `GOAWAY` with last stream 19999; HTTP/3: a close with `H3_NO_ERROR` and no `GOAWAY`), and a load was about
9,000 before the staged read. When the HTTP/2 `GOAWAY` arrives, Chrome retries the streams the server refused but
fails a few hundred requests it had queued with `ERR_FAILED`, never sent and never retried ([crbug 355006326]; the
cause is in `SpdySession`, `bugs/README.md`). The HTTP/3 close fails everything in flight. Either way about 5–30
cells read blank on most reloads on the live site; locally, over HTTP/1.1, never.

A lost probe either fails (`ERR_FAILED`: it looks like a miss) or hangs (sent, never answered, its `<img>` pending
for good). So a cell reads again, with fresh URLs, on either of two triggers:

- **at once**, when its 16 probes have all finished without a hit;
- **8 s after the second sentinel**, if it is still unread (this catches hung probes); 90 s after load if a sentinel
  itself fails. The sentinel no longer queues behind every probe (stage 2 is requested as stage 1 answers, partly
  after it), so the margin is wider than the old 3 s: at 3 s, `tools/goaway.js` loads re-read 200–260 cells whose
  stage 2 was still in flight; at 8 s, only the lost ones.

```css
.v2  { animation: go-late 0s 90s forwards }                                         /* --go: 1 */
@container s2 (width < 524px) { .v2 { animation: go 0s 8s forwards } }               /* second sentinel loaded */
@container (width < 17px) { .rt { display: if(style(--go: 1): block; else: none) } } /* still unread */
@container (height: 240px) { .rt { display: block } }                               /* all 16 probes missed */
```

- `.v2`'s height is 240 px exactly when stage 2's 15 probes have all missed (stage 1 missed too, or stage 2 wouldn't
  show); a hit anywhere makes it 225 px and the width 17 px or more.
- The sentinels: `<i style="content:url(/s.png)">` (no-store) comes after every stage-1 probe in the document, at the
  same priority, so it loads once stage 1 has gone out. `/s.png?2` is requested only when the first has loaded, so it
  queues behind the stage-2 probes and the requests a `GOAWAY` re-sent. Each sentinel narrows its own `.gd`
  container from outside: the `.sig` row is fixed width and the sentinel takes 8 px of it (the small-screen scale is
  on the outer `.sig`).
- `.rt` holds 16 probes `/c/k/r/2/<v>.png` (another `_redirects` rule onto `r/<v>.png`, inside the dictionary's
  `match`).
- A cell never written always pays its probes twice: "never written" and "read failed" look the same.

[crbug 355006326]: https://issues.chromium.org/issues/355006326

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

Every page URL is extensionless (`/c/k/x`, `/c/k/p/5`). Cloudflare redirects `*.html` to the extensionless path; a
redirect inside a 200 rewrite would leave the `/c/<k>/` namespace. Files keep `.html` on disk; Cloudflare and
`serve.js` serve `p/5.html` at `/p/5`.

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
  document; unlimited writes need a document per write, as the cells do.
