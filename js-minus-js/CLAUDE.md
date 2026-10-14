@AGENTS.md

## Claude-specific

- **Working with the user**:
  - Be terse and direct.
  - Explain your reasoning, not just the answer.
  - Cite a source for any claim about browser behaviour.
  - When reviewing code the user shares, critique it rather than rewrite it.
  - When sharing a code or config file, give the whole file unless asked for part.
- **Never merge into `main` until the user says so.** That covers merges of any kind, rebasing or
  cherry-picking onto it, and committing on it directly. Finish the work on a branch or worktree, report, and
  wait. A go-ahead for one merge doesn't cover the next.
- **Whenever you have something new for the user, build it and give them a link to test it by hand, plus the
  build's path.**
  - `make page` writes `build/js_in_css.xhtml` in that checkout or worktree. `dist/` is what `main` ships.
  - Serve the repo root in the background:
    `python3 -m http.server 8765 --bind 127.0.0.1 --directory /workspaces/css-energy` (VS Code forwards the port).
  - Link `http://localhost:8765/<path from the repo root>`, e.g.
    `http://localhost:8765/.claude/worktrees/<name>/js-minus-js/build/js_in_css.xhtml`.
  - Check the link with `curl -sI` first. The page must be served as `application/xhtml+xml`.
  - The link is in addition to the harnesses (AGENTS.md: test in a headless browser yourself), not instead of them.
- **When work stops before it's finished**, leave the files in a working state and say exactly what's left.
- **Skills** (in `.claude/skills/`):
  - `language-feature`: add a JavaScript feature end to end.
  - `rebuild-page`: rebuild and verify the page.
  - `benchmark`: measure and record performance.
- **Delegate log and trace digging to a subagent.** Chrome traces and harness logs are large; ask for the
  numbers, not the dump.
- **Run browser jobs in the background.** `make l3` takes about 1.5 minutes and `make l5` about 10. Redirect their
  output to a file and poll it, rather than blocking a tool call past its timeout.
- **When compacting**, preserve:
  - the list of modified files;
  - the last result of each test level (L1–L5) with its pass count;
  - any before/after measurements not yet written to `docs/BENCHMARKS.md`.
