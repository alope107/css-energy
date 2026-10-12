---
name: rebuild-page
description: Rebuild dist/js_in_css.xhtml from source and verify it end to end in headless Chromium (after any compiler, runtime-library, machine or readback change).
---
# Rebuild and verify the page

1. **Build.** Run `make page` (about 45 s). It rebuilds `compiler/lib.json` if `lib_src.js` changed, then
   `build/ccimg.json`, `build/f4cc_16.woff2` (the CPU font, with the lib baked into its ROM) and
   `build/js_in_css.xhtml`. Builds are reproducible: the same sources give the same bytes.
2. **Smoke-test.** Run `make l5-smoke` (about 2 minutes). Every line must say `"ok":true`. The `initial` run is
   FizzBuzz; its console is compared with Node's output, and it should halt about 32 s after Run. A `haltMs` near
   240000 means the harness gave up waiting.
3. **Full test, if the change could affect particular programs.** Run `make l5` in the background (about
   45 minutes):

   ```
   make l5 > build/l5.log 2>&1 &
   grep -c '"ok":true' build/l5.log
   ```
4. **Ship.** Run `make dist` to copy the page to `dist/`.
5. **Check timing.** If wall time matters to the change, compare FizzBuzz `haltMs` with `docs/BENCHMARKS.md`
   §A3. The noise is about ±1 s.
