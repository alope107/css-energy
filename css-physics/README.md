# rigid3d.css

A 3D rigid-body physics engine written in **CSS**, with no JavaScript in the page. Boxes and spheres fall, stack, slide, roll, bounce and fall asleep in a walled tray, and you can grab and throw them with the mouse or a finger. Chrome; Safari 26+, at two-thirds speed on a 60 Hz display; and Firefox 159+ (158 with `layout.css.scroll-driven-animations.enabled` in `about:config`), at about half speed.

The physics runs in the browser's style engine: about 170k custom-property declarations at 48 bodies, gated by `@container` queries, with state written into layout and read back every frame through scroll-driven animations.

## Quick start

```bash
npm install && npx playwright install chromium   # test tools only (in the devcontainer: npm install only)
COUNTS=16 PLAIN=1 python3 src/build3d.py out/p16.html     # one 16-body engine, readable names
bash tools/smoke.sh 16            # physics pass/fail check in headless Chromium
python3 src/build3d.py out/rigid3d.html   # the published pages: out/rigid3d-{8,16,24,32,48,64}.html
```

Open a built page in Chrome, Safari or Firefox; for 48 and 64, serve the folder, because they link split `.css` files. The page offers scenes (tower, rain, stack), gravity, shake and reset, and art styles (cel, pencil, wireframe, baroque, undulating, impressionist, Mondrian, oil, plasma, paper, pixel; [ARCHITECTURE](docs/ARCHITECTURE.md) §3).

## Status (Oct 2026)

| Bodies | Performance |
|---|---|
| 16 | about 50 fps in the first 3 s of chaos, then 60 fps |
| 48 | chaos 10–13 fps, drag 12 fps; settles in about 11 s |
| 48 (4 boxes, 44 spheres) | chaos 16–48 fps until it settles at 6 s, drag 25 fps |
| 64 | chaos 7–9 fps, drag 7 fps; dragging one body through a sleeping field about 24 fps |
| 96 | about 3.5 fps while everything is awake, about 12 fps with 4 bodies awake |

Headless Chromium 153 on an Intel i5-12600H mini PC without a GPU; an idle (all asleep) 32-body scene costs 3.6 ms of style per frame.

## Docs

[ARCHITECTURE](docs/ARCHITECTURE.md) (how it works), [BENCHMARKS](docs/BENCHMARKS.md) (measurements and the cost
model), [HISTORY](docs/HISTORY.md) (dead ends and open ideas), [experiments/](experiments/README.md) (the
microbenchmarks). Working on it: [CLAUDE.md](CLAUDE.md).
