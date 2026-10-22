# Dictionary Paint

A 16-colour canvas whose pixels persist in Chrome's compression-dictionary store, in HTML and CSS only. `build.py`
generates `site/`; `serve.js` serves it locally the way Cloudflare does (`_headers`, 200 `_redirects`). Read
`docs/ARCHITECTURE.md` before changing the generator; `docs/HISTORY.md` lists what already failed (check it before
proposing an idea).

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
- The tools launch Chromium through `../shared/js/browser.js` (profile `physics`, `../shared/README.md`), start their
  own `serve.js` on a free port, and use a fresh persistent profile per run.

## Commands (in `paint/`)
- Local server: `node serve.js site [port]` (default 8080). `--log` prints each request with the
  `Available-Dictionary` hash Chrome sent; `--delay MS` adds latency; `--fault target|strip|vary` simulates a broken host;
  `--goaway N` (HTTP/2, `--cert`/`--key`) ends each connection after N streams, as Cloudflare does after 10,000.
- Manual-test link for the user: `node serve.js site 8766` in the background, link `http://localhost:8766/`, check it
  with `curl -sI`. Not the repo-root `http.server`: it sends none of the headers, and nothing works without them.
- Rebuild: `python3 build.py [W] [H]` (cells ≤ 490). Self-test site: `python3 selftest/build.py`.
- Tests: `make test` = `node tools/selftest.js` (~10 s, its four hosts at once: `SHARDS`), `node tools/e2e.js [seed]`
  (~1.5 min, mouse) and `node tools/touch.js` (~40 s, finger strokes on a phone viewport); `make test-goaway` (~2 min,
  needs openssl) checks reads over an HTTP/2 host that ends connections like Cloudflare. Through `make`, a test whose site, tools and browser haven't changed since it passed prints `up to date`;
  `RERUN=1` runs it.
  Long runs exceed default tool timeouts: write output to a file and poll it.

## Non-obvious gotchas
- **Registering a dictionary** needs a fresh-cacheable response (`max-age` > 0; `no-cache`/`no-store`/`max-age=0`
  never register), `Vary: *` (else Blink's memory cache serves a reused write URL and nothing registers), and, for
  image-loaded dictionaries, valid image bytes (the decoder cancels an invalid load before Chrome stores it).
- Destinations that register: `mask-image`, `filter: url()`, `@font-face`, `@import`, lazy `<img>`,
  `<link rel=prefetch|preload|compression-dictionary>`. Not `background-image`, `cursor`, iframe or object documents.
- **One fetch per URL per document.** A document can write each (cell, value) URL once; the writers write
  `d/<v>.png?<slot>`, and a per-cell clock moves to a new slot on every change (`docs/ARCHITECTURE.md#writes`).
- **A press is captured by the frame it starts in**: a drag that starts in an `<object>`/iframe never reaches
  another frame (nor the page's `:hover`). Input lives in the page; frames get `pointer-events: none`.
- **Hiding a loaded `<object>` keeps its document**: re-showing it loads nothing. Only a first show loads.
- Don't gate an animation on transition-animated values of the same element (`animation-play-state:
  if(style(--L: var(--W)))`): it isn't recomputed when the transition ends. Compute a difference on a child and test
  it on a grandchild (the cell clock does).
- **History traversal serves every CSS-initiated fetch from cache**, and a cached response never registers. Only
  `<link rel=compression-dictionary>` goes to the network on Back/Forward. It is fetched when the network is idle:
  ~150 ms normally, ~30 s while the page is still probing. The link's `media` attribute is ignored. (Back/Forward
  undo is gone since October 2026, `docs/HISTORY.md` §8.)
- **Chrome allows about 1,000 frames per page.** Every `<iframe>` takes one, even hidden and `loading=lazy`; a
  hidden `<object>` takes none and loads nothing. That is why the writers are `<object>`s, shown only once a cell is
  painted; each shown writer keeps its frame for the page's life.
- **Reads must be in one document.** 480 frames each firing 16 probes put ~7,700 requests in flight; Chrome rejects
  the excess before sending and never retries. One document's loader throttles itself.
- URLPattern: `match="/r/*?k-*"` never matches (`*?` is an optional wildcard). Put a literal before `?`:
  `match="/r/*.png?k-*"`.
- Cloudflare redirects `*.html` to the extensionless path, which inside a 200 rewrite would leave the cell's
  `/c/<k>/` namespace: every page URL is extensionless. Pages joined a header set by two `_headers` rules with `, `
  (unchecked on Workers): no overlapping rules (a joined `Cache-Control` containing `no-cache` stops registration).
- A spinner still showing on a cell means its write hasn't loaded: a reload then can lose it. `tools/e2e.js`
  waits for each writer's current URL in its `performance` entries before reloading.
- Touch uses css-physics's handles, but the dragged handle **publishes** its drag as an anchor's size
  (`docs/ARCHITECTURE.md#touch`): don't sum hundreds of handles with `timeline-scope`d timelines, each consumer costs
  ~0.1 ms per layout (960 made every layout ~94 ms). The stroke values are `inherits: false` and each element that
  needs them takes them with `inherit` (the follower `.fo` sits inside `.grid` for this).
- Time things under the bench lease (`../.claude/worktrees/bench-queue/shared/py/bench.py run -m p -- …` until it is
  merged): other sessions benchmark on this machine, and an unleased run lands on the E-cores.
- **Cloudflare ends each connection after ~10,000 requests** (HTTP/2 `GOAWAY`, HTTP/3 close), and a load is ~9,000.
  Chrome then fails a few hundred queued probes with `ERR_FAILED` and doesn't retry them (crbug 355006326): ~5–30
  blank cells per reload, live only. The page's retry row covers it (`docs/ARCHITECTURE.md#retry`); local HTTP/1.1
  never shows it, so test it with `serve.js --goaway`.
- Label the CSS you add (`lbl.section` / `lbl.group` in build.py; `../shared/README.md#labels-in-generated-css`). The
  writer page gets short labels without notes: every painted cell loads one. `python3 ../shared/py/csslabel.py
  site/index.html` prints the page's outline.
- `ERR_UNEXPECTED_CONTENT_DICTIONARY_HEADER` in the console is a probe answering "no" (15 per painted cell).
- `--ignore-certificate-errors` disables HTTP caching, so dictionaries never register. Trust a test cert by SPKI
  (`--ignore-certificate-errors-spki-list=<hash>`) or use `http://localhost`.
- Playwright: frames detached by a reload stay in `childFrames()`; filter `isDetached()` and pick the visible
  `<object>` (a cell's earlier writers stay attached, hidden).
