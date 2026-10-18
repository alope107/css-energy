---
name: rebuild-page
description: Rebuild dist/js_in_css.xhtml from source and verify it end to end in headless Chromium (after any compiler, runtime-library, machine or readback change).
---
# Rebuild and verify the page

1. **Build**: `make page` (~25 s, reproducible). It rebuilds `compiler/lib.json` if `lib_src.js` changed, then
   `build/ccimg.json`, `build/f4cc_16.woff2` (the CPU font, lib baked into its ROM) and `build/js_in_css.xhtml`.
2. **Smoke-test**: `make l5-smoke` (~1 min). Every line must say `"ok":true`. `initial` is FizzBuzz, compared with
   Node's output. A `haltMs` near 240000 means the harness gave up waiting.
3. **Full test**, if the change could affect particular programs: `make l5 > build/l5.log 2>&1 &` (~10 min), then
   `grep -c '"ok":true' build/l5.log`.
4. **Ship**: `make dist`.
5. **Timing**, if wall time matters: compare FizzBuzz `haltMs` with `docs/BENCHMARKS.md` §5a, or better, A/B the old
   and new page (`.claude/skills/benchmark`).
