# rigid3d.css

A 3D rigid-body physics engine written in **CSS**, with no JavaScript in the page. Boxes and spheres fall, stack, slide, roll, bounce and fall asleep in a walled tray, and you can grab and throw them with the mouse or a finger. Chrome, and Firefox 159+ (Firefox 158 with `layout.css.scroll-driven-animations.enabled` in `about:config`), where it runs at about half speed on a 60 Hz display.

The physics runs in the browser's style engine: about 170k custom-property declarations (about 25k registered properties) at 48 bodies, gated by `@container` queries. State is written into layout and read back every frame through scroll-driven animations (view timelines). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

```bash
npm install && npx playwright install chromium   # test tools only; building needs just Python 3
COUNTS=16 PLAIN=1 python3 src/build3d.py out/p16.html     # one 16-body engine, readable names
bash tools/smoke.sh 16            # physics pass/fail check in headless Chromium
bash tools/make_site.sh           # the published pages: site/rigid3d-{8,16,24,32,48,64}.html
```

Open a built page in Chrome or Firefox; for 48 and 64, serve or open the folder, because they link split `.css` files. The page offers scenes (tower, rain, stack), gravity, shake and reset.

## Layout

| Path | What |
|---|---|
| `src/gen3d.py` | the engine generator (one engine per body count) |
| `src/build3d.py` | page builder (single page, multi-engine page, or one page per count) |
| `src/simp.py` | calc() expression simplifier |
| `src/page3d.html`, `src/ui3d.css` | page template and UI/render CSS |
| `tools/` | headless-Chromium harnesses: smoke test, profiling, fps, freeze/ablate |
| `experiments/` | microbenchmarks behind the cost model: style costs, variable fonts as compute, compositor interpolation, iframe processes, `ident()` |
| `archive/` | the pre-optimization 3D generator, still buildable as an A/B baseline; README.md indexes the removed 2D engine |
| `docs/` | ARCHITECTURE (how it works), HISTORY (how we got here and what failed), BENCHMARKS (all measurements) |

## Status (Oct 2026)

| Bodies | Performance |
|---|---|
| 16 | about 50 fps in the first 3 s of chaos, then 60 fps |
| 48 | chaos 10–13 fps, drag 12 fps; settles in about 11 s |
| 48 (4 boxes, 44 spheres) | chaos 16–48 fps until it settles at 6 s, drag 25 fps |
| 64 | chaos 7–9 fps, drag 7 fps; dragging one body through a sleeping field about 24 fps |
| 96 | about 3.5 fps while everything is awake, about 12 fps with 4 bodies awake |

Measured on the Ubuntu mini PC (Intel i5-12600H), headless Chromium 153 (docs/BENCHMARKS.md, 2026-10-17); a desktop with a GPU is faster. Idle scenes cost about 1 ms of style per frame. Spatial partitioning of the broadphase was built and measured (2026-10-13) and does not pay in this design: the all-pairs digest charges only awake bodies, and the N² floor is the static per-pair rules (docs/HISTORY.md).
