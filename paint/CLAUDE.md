# Dictionary Paint

A 16-colour canvas whose pixels persist in Chrome's compression-dictionary store, in HTML and CSS only. `build.py`
generates `site/`; `serve.js` serves it locally with Cloudflare Pages semantics. Read `docs/ARCHITECTURE.md` before
changing the generator; `docs/HISTORY.md` lists what already failed (check it before proposing an idea).

## Hard rules
- IMPORTANT: the pages contain **no JavaScript**, ever, unless the user explicitly asks. JS is fine in `tools/`,
  `serve.js` and other harnesses.
- **Static hosting only.** A response may depend on its path, never on request headers (`Available-Dictionary`
  included): `_headers` and `_redirects` only, no Worker or server logic.
- Chrome/Chromium only.
- Verify in headless Chromium yourself (`make test`); don't hand the user something you can test.
- **Never change the bytes of `site/d/*.png`.** Visitors' browsers hold those dictionaries; new bytes make every
  stored canvas read as blank. `build.py` keeps existing files; delete them only to deliberately reset everyone.

## Setup
- Node 18+ for `serve.js` (no dependencies). `npm install` for the tools (Playwright).
- Python 3 + `pip install -r requirements.txt` (zstandard) to rebuild.
- The tools launch Chromium through `../shared/js/browser.js`, profile `physics` (`--no-sandbox`; `CHROME=/path`
  overrides). They start their own `serve.js` on a free port and use a fresh persistent profile per run.

## Commands (in `paint/`)
- Local server: `node serve.js site [port]` (default 8080). `--log` prints each request with the
  `Available-Dictionary` hash Chrome sent; `--delay MS` adds latency; `--fault target|strip|vary` simulates a broken host.
- Manual-test link for the user: `node serve.js site 8766` in the background, link `http://localhost:8766/`, check it
  with `curl -sI`. Not the repo-root `http.server`: it sends none of the headers, and nothing works without them.
- Rebuild: `python3 build.py [W] [H]` (cells ≤ 490). Self-test site: `python3 selftest/build.py`.
- Tests: `make test` = `node tools/selftest.js` (~1 min) then `node tools/e2e.js [seed]` (~6 min). Long runs exceed
  default tool timeouts: write output to a file and poll it.

## Non-obvious gotchas
- **Registering a dictionary** needs a fresh-cacheable response (`max-age` > 0; `no-cache`/`no-store`/`max-age=0`
  never register), `Vary: *` (else Blink's memory cache serves a reused write URL and nothing registers), and, for
  image-loaded dictionaries, valid image bytes (the decoder cancels an invalid load before Chrome stores it).
- Destinations that register: `mask-image`, `filter: url()`, `@font-face`, `@import`, lazy `<img>`,
  `<link rel=prefetch|preload|compression-dictionary>`. Not `background-image`, `cursor`, iframe or object documents.
- **One fetch per URL per document.** A document can write each (cell, value) URL once; unlimited writes come from
  new documents (painting navigates the cell's `<object>`).
- **History traversal serves every CSS-initiated fetch from cache**, and a cached response never registers. Only
  `<link rel=compression-dictionary>` goes to the network on Back/Forward. It is fetched when the network is idle:
  ~150 ms normally, ~30 s while the page is still probing. So painted pages write both ways (mask-image now, link
  for undo/redo). The link's `media` attribute is ignored.
- **Chrome allows about 1,000 frames per page.** Every `<iframe>` takes one, even hidden and `loading=lazy`; a
  hidden `<object>` takes none and loads nothing. That is why each cell has 16 `<object>`s.
- **Reads must be in one document.** 480 frames each firing 16 probes put ~7,700 requests in flight; Chrome rejects
  the excess before sending and never retries. One document's loader throttles itself.
- URLPattern: `match="/r/*?k-*"` never matches (`*?` is an optional wildcard). Put a literal before `?`:
  `match="/r/*.png?k-*"`.
- Cloudflare Pages redirects `*.html` to the extensionless path, which inside a 200 rewrite would leave the cell's
  `/c/<k>/` namespace: every page URL is extensionless. Pages also joins a header set by two `_headers` rules with
  `, `: no overlapping rules (a joined `Cache-Control` containing `no-cache` stops registration).
- Painting a cell its current colour is a same-URL navigation: Chrome replaces the history entry, so it is not an
  undo step (tests must paint a different colour before Back).
- `ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER` in the console is a probe answering "no" (15 per painted cell).
- `--ignore-certificate-errors` disables HTTP caching, so dictionaries never register. Trust a test cert by SPKI
  (`--ignore-certificate-errors-spki-list=<hash>`) or use `http://localhost`.
- Playwright: frames detached by a reload stay in `childFrames()`; filter `isDetached()` and pick the visible
  `<object>`. `page.goBack()` waits for a top-level navigation; drive undo with CDP `Page.navigateToHistoryEntry`.
