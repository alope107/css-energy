# Dictionary Paint

A 24×20, 16-colour canvas in **HTML and CSS**, with no JavaScript in the page, whose pixels are stored in Chrome's
compression-dictionary store. Click or drag to paint, with a mouse or a finger; a cell shows its colour at once and a
spinner until it is stored; unpainted cells are checkered. The picture survives reloads and browser restarts. Chrome only. Hosting is static files plus Cloudflare-style `_headers` and
`_redirects`; nothing on the server looks at a request.

Every cell is one shared-dictionary entry, and its colour is which of 16 dictionary files it holds. Writing is
loading a file that a response header marks `Use-As-Dictionary`. Reading is 16 probe images, each compressed
against one of the 16 dictionaries: only the probe that matches the stored dictionary decodes, and its width tells
CSS the value. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Live: https://paint.auberon.workers.dev/ (pushing to `main` deploys `site/`, `../deploy/README.md`).

## Quick start

```bash
node serve.js site                    # http://localhost:8080/, applying site/_headers and site/_redirects
npm install                           # test tools only: Playwright
make test                             # self-test site against simulated host faults, then the end-to-end test (~1.5 min)
pip install -r requirements.txt       # zstandard, only to rebuild
python3 build.py 24 20                # W H (at most 490 cells) -> site/, keeping the existing dictionaries
```

`http://localhost` is a secure context, so dictionaries work without HTTPS. For HTTP/2 the certificate must be
trusted (`mkcert localhost`, then `node serve.js site 8443 --cert localhost.pem --key localhost-key.pem`): with a
self-signed one Chrome stops caching and no dictionary registers.

**Keep `site/d/*.png` across deploys:** visitors' browsers hold those exact bytes, and new ones make every stored
canvas read as blank.

## Host self-test

Before using a new host, deploy `selftest/site/` there, open it in a fresh Chrome profile, reload once, and follow
test D's four-page chain:

| Test | Checks | If it fails |
|---|---|---|
| A | `Use-As-Dictionary` and `Content-Encoding: dcz` reach Chrome | the host strips them; on Cloudflare set Speed → Shared dictionaries to passthrough |
| B | `:placeholder` substitution in `_headers` values | no per-cell match patterns |
| C | `_headers` apply to the request path of a 200 rewrite; cells stay separate | you'd need one file per (cell, value) |
| D | `Vary: *` survives | never reuse a write URL within one tab |

`node tools/selftest.js` checks the self-test page against each `serve.js --fault`.

## Layout

| Path | What |
|---|---|
| `build.py` | site generator: dictionaries, probes, the writer page, the page, `_headers`, `_redirects` |
| `site/` | the deployable site (prebuilt) |
| `serve.js` | local static server applying `_headers` and 200 `_redirects`; `--fault`, `--goaway` simulate host behaviour |
| `selftest/` | the host self-test page (`selftest/build.py` builds `selftest/site/`) |
| `tools/` | headless-Chromium harnesses: `e2e.js` (the canvas, mouse), `touch.js` (finger strokes), `selftest.js`, `goaway.js` |
| `docs/` | ARCHITECTURE, HISTORY (what failed), BENCHMARKS |

## Status (Oct 2026)

- `make test` passes in headless Chromium 153: `tools/e2e.js` (clicks, drags, strokes that jump 6 cells a frame
  drawn as whole lines, 40 changes of one cell, palette change, reload, repaints, browser restart) and
  `tools/touch.js` (finger strokes on a phone viewport: slow, quick, back and forth, fast diagonal, tap).
- No undo: Back/Forward undo went with the cell documents (docs/HISTORY.md, 8). A cell can change about 110 times
  per page load before its writes stop (its spinner then stays); a reload resets that.
- A touch stroke trails the finger by the touch slop, about a cell on a phone.
- The click-only canvas worked on Cloudflare Workers; this version (writers at `/c/<k>/w`, write URLs with a
  `?<slot>` query) hasn't been deployed yet. The console shows `ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER` 15 times per painted cell:
  the probes answering "no". Cloudflare ends connections after ~10,000 requests and Chrome drops some queued probes;
  a retry pass re-reads those cells (docs/ARCHITECTURE.md, "Retry").
- First load reads 480 cells with 7,680 probes: about 25–45 s in a slow headless sandbox.
- Capacity: 500 dictionaries per top-level site, log₂K bits each; this canvas uses 480 × 4 bits.
