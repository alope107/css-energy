# Benchmarks

Measured in headless Chromium 153.0.8010.12 (Playwright's build) and, where marked, 141.0.7390.37, in a cloud
sandbox: a slower machine than the Ubuntu mini PC the other projects' numbers come from, and without a GPU. Servers
were local: Python's `http.server` (HTTP/1.1, one connection per request), a Node HTTP/2 server, and `serve.js`.
Compare numbers within this file, not with the other projects'.

## Capacity

| What | Value | Source |
|---|---|---|
| Dictionaries per profile | 1,000 | `kDictionaryMaxCountPerNetworkContext` |
| Dictionaries per top-level site | 500 | `cache_max_count_per_site() = cache_max_count_ / 2`; 512 written, 12 lost (141) |
| Two sites | 480 + 480, 0 lost | measured (153) |
| Frames under one site | share its 500 | 4 frames of other origins × 480 random bits: about 110–170 survive each (estimated from mismatch counts) |
| Frames per page | ~1,000 | 17 `<iframe>`s per cell: loads stopped at cell 59 (1,000 frames) |

## Correctness (all 0 errors)

| Test | Result |
|---|---|
| K = 2, 500 cells, 5 random rewrite rounds + browser restart | 0 errors |
| K = 16, 480 cells, 2 rounds + restart | 0 errors |
| K = 256, 480 cells written, 40 read per round, HTTP/1.1 and HTTP/2, + restart | 0 errors |
| K = 4096, 480 cells written, 6 read, HTTP/2, + restart | 0 errors |
| Canvas, end to end (`tools/e2e.js` and its Python predecessor, seeds 3 and 11, HTTP/1.1 and HTTP/2) | 0 mismatches |

## Read throughput

Probes cost the same as plain images; the limit is requests per second.

| Server | Plain images | dcz probes |
|---|---|---|
| Python `http.server`, HTTP/1.1 | 108 /s | 111 /s |
| Node HTTP/2 | 345 /s | 299 /s |

| Read | Requests | Time | Server |
|---|---|---|---|
| K = 16, 480 cells | 7,680 | 48–51 s | Python HTTP/1.1 |
| K = 256, 40 cells | 10,240 | 66–67 s | Python HTTP/1.1 |
| K = 256, 40 cells | 10,240 | 34–41 s | Node HTTP/2 |
| K = 4096, 6 cells | 24,576 | 208 s (24k images on one page) | Node HTTP/2 |

## The canvas

| Measure | Value |
|---|---|
| First load, page + 480 cell documents + 7,680 probes | 25–47 s (HTTP/2 or HTTP/1.1, `serve.js`; before the staged read) |
| Staged read (2026-10-18, mini PC, local HTTP/1.1): 480 cells, a third colour 1, a third other colours, a third blank | 7,690 probes vs 10,240 before; read in 11.9–12.0 s vs 11.2–13.5 s before (`survey`-style harness, two runs each) |
| Staged read, `tools/goaway.js` canvas (480 random colours, 1/16 colour 1), HTTP/2 ending connections after 2,000 requests | every cell read in 5 of 5 loads (the design before: 5 of 5); retries exactly 16 probes per lost cell; loads 26–33 s vs 20–25 s before |
| Writes, 480 cells at once | 2.5–5.6 s |
| `<link rel=compression-dictionary>` delay after its page loads | ~120–180 ms idle; ~24–30 s while the page is still probing |
| Live (Cloudflare Workers): cells the first pass loses per reload | 0–31, most loads; HTTP/2 `GOAWAY` or HTTP/3 close after ~10,000 requests per connection (HISTORY §6) |
| Workers preview: first pass lost / after the retry | 0–32 / 0 per load, 5 loads |
| Local HTTP/2, `--goaway 10000`: first pass lost / after the retry | 0–32 / 0 per load, 11 loads; the retry sends 16 probes per lost cell, 3 s after the second sentinel (before the staged read); staged read: 0–24 / 0, 5 loads |
| Console errors per load | 15 `ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER` per painted cell (7,200 with 480 painted); 0 from cells never written |
| Files deployed | 53 (`site/`), 5 dynamic `_redirects` rules, 6 `_headers` rules |

## Against the other projects' RAM

| | In-page CSS RAM (js-minus-js `memtree.py` design) | Dictionary store |
|---|---|---|
| Read | ~0.2 ms per chained read, within one layout pass *(an earlier session's benchmark, not in js-minus-js's BENCHMARKS.md)* | K requests; at best one network round trip |
| Write | ~5 µs of style per written cell *(same)* | one request plus a disk commit; ~100–190 writes/s in a batch |
| Survives reload | no | yes |

The store is a disk, not RAM: read it once at boot, write back.
