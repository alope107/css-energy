# css-energy

Two projects: `css-physics/` and `js-minus-js/`, each with its own CLAUDE.md. `COMPARISON.md` compares their
techniques.

## User rules (all projects)

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
| css-physics | `python3 src/build3d.py out/<name>.html` (in `css-physics/`) | `css-physics/out/<name>.html` |
