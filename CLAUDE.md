# css-energy

Two projects: `css-physics/` and `js-minus-js/`, each with its own CLAUDE.md. `COMPARISON.md` compares their
techniques.

## Shared code

- `shared/` is harness code both projects' tools use: browser launch profiles, tracing, A/B timing, motion checks,
  freezing, ablation (`shared/README.md`). Each project's commands are unchanged. A change there touches both: run
  `make test-shared`, css-physics `bash tools/smoke.sh 16`, and js-minus-js `make test`, `make l3`, `make l5-smoke`.
- The two projects launch Chromium with different flags (`shared/js/browser.js` profiles). Their benchmark numbers
  were taken with those flags; don't unify them without re-measuring both.
- `engine/` checks the Chrome behaviour both projects depend on: `make engine-check` (facts, pass/fail, ~20 s) and
  `make engine-costs` (the style-engine cost table against the docs, ~2 min, no other browser jobs). Run both after a
  Chrome upgrade; `engine/README.md` lists the facts and which notes cite them.

## User rules (all projects)

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
