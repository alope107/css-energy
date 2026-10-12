@AGENTS.md

## Claude-specific

- **Working with the user**:
  - Be terse and direct.
  - Explain your reasoning, not just the answer.
  - Cite a source for any claim about browser behaviour.
  - When reviewing code the user shares, critique it rather than rewrite it.
  - When sharing a code or config file, give the whole file unless asked for part.
- **When work stops before it's finished**, leave the files in a working state and say exactly what's left.
- **Skills** (in `.claude/skills/`):
  - `language-feature`: add a JavaScript feature end to end.
  - `rebuild-page`: rebuild and verify the page.
  - `benchmark`: measure and record performance.
- **Delegate log and trace digging to a subagent.** Chrome traces and harness logs are large; ask for the
  numbers, not the dump.
- **Run browser jobs in the background.** `make l3` takes about 3 minutes and `make l5` about 45. Redirect their
  output to a file and poll it, rather than blocking a tool call past its timeout.
- **When compacting**, preserve:
  - the list of modified files;
  - the last result of each test level (L1–L5) with its pass count;
  - any before/after measurements not yet written to `docs/BENCHMARKS.md`.
