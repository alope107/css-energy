# css-energy

Three projects: `css-physics/`, `js-minus-js/` and `paint/`, each with its own CLAUDE.md. `COMPARISON.md` compares
their techniques.

## Shared code

- `shared/` is harness code the projects' tools use: browser launch profiles, tracing, A/B timing, motion checks,
  freezing, ablation (`shared/README.md`). Each project's commands are unchanged. A change there touches all of them:
  run `make test-shared`, css-physics `bash tools/smoke.sh 16`, js-minus-js `make test`, `make l3`, `make l5-smoke`,
  and, for `browser.js`, paint `make test`.
- css-physics and js-minus-js launch Chromium with different flags (`shared/js/browser.js` profiles). Their
  benchmark numbers were taken with those flags; don't unify them without re-measuring both. paint's tools use the
  `physics` profile.
- `engine/` checks the Chrome behaviour css-physics and js-minus-js depend on: `make engine-check` (facts,
  pass/fail, ~20 s) and `make engine-costs` (the style-engine cost table against the docs, ~2 min, no other browser
  jobs). Run both after a Chrome upgrade; `engine/README.md` lists the facts and which notes cite them. paint's facts
  (dictionary registration rules, the frame limit) are checked by its own `make test`.

## Deploys

- `.github/workflows/deploy.yml` deploys to Cloudflare Pages: `main` → production, any other branch → a preview of
  the projects it changed. `deploy/README.md` has the setup and the trust model.
- **Pushing a branch publishes a public preview: push only when the user asks.** Then `deploy/status.sh` waits for
  the run and prints the preview URLs; give the user the `<hash>` URL along with the local link.
- `deploy/assemble.sh <project> <dir>` builds exactly what CI deploys. `npx wrangler pages dev <dir>` emulates Pages
  for a check, but opens ~7 ports per instance: stop it afterwards, and don't use it for hand-test links.
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
