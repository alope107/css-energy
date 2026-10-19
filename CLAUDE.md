# css-energy

Three projects: `css-physics/`, `js-minus-js/` and `paint/`, each with its own CLAUDE.md. `COMPARISON.md` compares
their techniques.

## Shared code

- `shared/` is harness code the projects' tools use: browser launch profiles, tracing, A/B timing, motion checks,
  freezing, ablation (`shared/README.md`). Each project's commands are unchanged. A change there touches all of them:
  run `make test-shared`, css-physics `bash tools/smoke.sh 16`, js-minus-js `make test`, `make l3`, `make l5-smoke`,
  and, for `browser.js` or `csslabel.py`, paint `make test`.
- Generated CSS is labelled: a header, then `/* === Section === */` and `/* --- Group --- */` comments, written
  through `shared/py/csslabel.py` by every generator, which fails the build if a rule comes before the first section.
  Label new CSS as you add it; the conventions are in `shared/README.md#labels-in-generated-css`.
  `python3 shared/py/csslabel.py <page>` prints a built page's outline.
- css-physics and js-minus-js launch Chromium with different flags (`shared/js/browser.js` profiles). Their
  benchmark numbers were taken with those flags; don't unify them without re-measuring both. paint's tools use the
  `physics` profile.
- `engine/` checks the Chrome behaviour css-physics and js-minus-js depend on: `make engine-check` (facts,
  pass/fail, ~20 s) and `make engine-costs` (the style-engine cost table against the docs, ~2 min, no other browser
  jobs). Run both after a Chrome upgrade; `engine/README.md` lists the facts and which notes cite them. paint's
  dictionary registration rules are checked by its own `make test`; its frame limit (~1,000 per page) isn't checked.

## Checks in make

- The slow checks are make targets that make skips while nothing they depend on changed since they last passed
  (css-physics `smoke.sh`, js-minus-js `make l2`, `fuzz`, `l3`, `l5`, `l5-smoke`, `l5-input`, paint `make test`,
  `make engine-check`). A skipped check prints `up to date: … passed <time>` and the end of that pass's log.
- **The evidence before a merge is a real run: `RERUN=1`** (`RERUN=1 make l3`, `RERUN=1 bash tools/smoke.sh 16`).
  Use it for a suspected flake too. When you paste an `up to date` result while iterating, say it wasn't re-run.
- `shared/README.md#checks-in-make` says what each check depends on and what make can't see.
- js-minus-js's checks and paint's self-test run in parallel (`JOBS`, `SHARDS`), with the serial run's verdicts.
  css-physics's `smoke.sh` runs in real time, one check at a time: start it alone, with no other browser job or fuzz
  running beside it (`shared/README.md#parallel-runs`).

## Browser bugs

The projects lean on corners of the engines, so they run into browser bugs. Don't go looking for them, but when one
turns up (a wrong result, an invalidation that doesn't happen, a crash, a spec violation, in any browser):
- Research it: the spec text, the browser's tracker (bugzilla.mozilla.org's REST API, issues.chromium.org,
  bugs.webkit.org), WPT coverage, and the engine source if that helps.
- If it's already reported, note the report in `bugs/README.md`. If not, write a minimal reproduction in `bugs/`: one
  self-contained HTML file, pass/fail visible without script, the observed results and spec text in a closing comment
  (`bugs/README.md` has the conventions), and list it there.
- Don't file reports: the user reviews the MREs and files them.

## Deploys

- `.github/workflows/deploy.yml` deploys to Cloudflare Workers (`*.auberon.workers.dev`): `main` → production,
  any other branch → a preview of the projects it changed. `deploy/README.md` has the setup and the trust model.
- **Pushing a branch publishes a public preview: push only when the user asks.** Then `deploy/status.sh` waits for
  the run and prints the preview URLs; give the user the `<version>` URL along with the local link.
- `deploy/assemble.sh <project> <dir>` builds exactly what CI deploys.
- Stop every server you start except the ones you hand to the user. Stray ports make VS Code stop auto-forwarding.

## User rules (all projects)

- Be terse and direct.
- Explain your reasoning, not just the answer.
- **Never touch anything under `.auberon/`.** It holds the user's own worktrees. Don't create, edit, delete or build
  files there. Read them only when the user points you at them. Put examples and builds in your own branch or worktree instead.
- **Never merge into `main` until the user says so.** That covers merges of any kind, rebasing or cherry-picking
  onto it, and committing on it directly. Finish the work on a branch or worktree, report, and wait. A go-ahead
  for one merge doesn't cover the next.
- **Whenever you have something new for the user, build it and give them a link to test it by hand, plus the
  build's path.**
  - Serve the repo root in the background:
    `python3 -m http.server 8765 --bind 127.0.0.1 --directory /workspaces/css-energy` (VS Code forwards the port).
  - Link `http://localhost:8765/<path from the repo root>`. A worktree's build is under
    `.claude/worktrees/<name>/`.
  - Check the link with `curl -sI` before handing it over.
  - This is on top of the project's own tests, not instead of them: run those first, as each CLAUDE.md says.

| Project | Build | Lands in |
|---|---|---|
| js-minus-js | `make page` (in `js-minus-js/`) | `js-minus-js/build/js_in_css.xhtml` |
| css-physics | `python3 src/build3d.py out/<name>.html` (in `css-physics/`) | `css-physics/out/<name>.html` (the 16-body page; it links `<name>-N.html` for 8–64) |
| paint | `python3 build.py` (in `paint/`) | `paint/site/`. It needs response headers the repo-root `http.server` doesn't send: serve it with `node serve.js site 8766` (in `paint/`) and link `http://localhost:8766/` |
