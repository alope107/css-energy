# Dictionary Paint

A 24×20, 16-colour canvas in **HTML and CSS**, with no JavaScript in the page, whose pixels are stored in Chrome's
compression-dictionary store. Paint as much as you like; Back and Forward are undo and redo; the picture survives
reloads and browser restarts. Chrome only. Hosting is static files plus Cloudflare-style `_headers` and
`_redirects`; nothing on the server looks at a request.

Every cell is one shared-dictionary entry, and its colour is which of 16 dictionary files it holds. Writing is
loading a file that a response header marks `Use-As-Dictionary`. Reading is 16 probe images, each compressed
against one of the 16 dictionaries: only the probe that matches the stored dictionary decodes, and its decoded
width tells CSS the value. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

```bash
node serve.js site                    # http://localhost:8080/ (applies site/_headers and site/_redirects like Pages)
npm install                           # test tools only: Playwright
make test                             # self-test site against simulated host faults, then the end-to-end test (~7 min)
pip install -r requirements.txt       # zstandard, only to rebuild
python3 build.py 24 20                # W H (at most 490 cells) -> site/, keeping the existing dictionaries
```

`http://localhost` is a secure context, so dictionaries work without HTTPS. For HTTP/2 (much faster probes) the
certificate must be trusted (`mkcert localhost`, then `node serve.js site 8443 --cert localhost.pem --key
localhost-key.pem`): with a self-signed one Chrome stops caching responses and no dictionary ever registers.

Deploy: `npx wrangler pages deploy site --project-name dictionary-paint`, or upload `site/` in the dashboard. Keep
`site/d/*.png` across deploys: visitors' browsers hold those exact bytes, and new ones make every stored canvas read
as blank.

## Host self-test

Before deploying to a new host, deploy `selftest/site/` there, open it in Chrome (a fresh profile or Incognito),
reload once, and follow test D's four-page chain. Each light checks one thing the canvas depends on:

| Test | Checks | If it fails |
|---|---|---|
| A | `Use-As-Dictionary` and `Content-Encoding: dcz` reach Chrome | the host strips them; on Cloudflare set Speed → Shared dictionaries to passthrough on your own zone |
| B | `:placeholder` substitution in `_headers` values | no per-cell match patterns |
| C | `_headers` apply to the request path of a 200 rewrite; cells stay separate | you'd need one file per (cell, value) |
| D | `Vary: *` survives | never reuse a write URL within one tab |

`node tools/selftest.js` checks the page itself: all PASS on a correct host, and the matching light for each
`serve.js --fault`.

## Layout

| Path | What |
|---|---|
| `build.py` | site generator: dictionaries, probes, cell pages, the page, `_headers`, `_redirects` |
| `site/` | the deployable site (prebuilt) |
| `serve.js` | local static server with Pages semantics for `_headers` and 200 `_redirects`; `--fault` simulates broken hosts |
| `selftest/` | a no-JS page that checks a host passes the four things the canvas needs (`selftest/build.py` builds `selftest/site/`) |
| `tools/` | headless-Chromium harnesses: `e2e.js` (the canvas), `selftest.js` (the self-test page against `--fault`) |
| `docs/` | ARCHITECTURE (how it works), HISTORY (how we got here and what failed), BENCHMARKS (measurements) |

## Status (Oct 2026)

- `tools/e2e.js` passes in headless Chromium 153: 65 paints (one cell 25 times), palette change, reload, undo and
  redo (live and after reload), page-to-page undo, a fast repaint with an immediate reload, browser restart.
- The self-test passed on a Cloudflare deployment, and the canvas works there. Console errors
  `ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER` are expected: 15 per painted cell, the probes that answer "no". An
  occasional `ERR_FAILED` on a probe, seen only on Cloudflare (HTTP/3), is not explained yet; it may drop a pixel
  from one load's read without touching the stored value (docs/HISTORY.md, open questions).
- First load reads 480 cells with 7,680 probes: about 25–45 s in a slow headless sandbox (docs/BENCHMARKS.md).
- Capacity: 500 dictionaries per top-level site, log₂K bits each; this canvas uses 480 × 4 bits.

## Project rules

- **No script on the pages.** Harness scripts are fine.
- **Chrome only.**
- **Static hosting only.** Responses may depend on the path, never on request headers: `_headers` and
  `_redirects`, no Worker or server code.
