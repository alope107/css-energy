# Face widgets

The engine with real HTML on its box faces: 4 big boxes (a TV, a control cube, a brick, a book) and 4 spheres
(`bodies.json`, through gen3d's `BODIES_JSON` knob), and on every face a control: buttons, checkboxes, radios, a
select, text fields, a textarea, `<details>`, a `<video>`, a `<marquee>`, an editable scrolling text, a date input.
Still no script. Some controls feed the inputs the page's own controls use, with `:has()`:

| Control | Where | Does |
|---|---|---|
| SHAKE button | cube, front | `--kick` while held |
| zero g / gravity ↑ checkboxes | cube, back / top | `--gy` 0 / −1600 |
| the magic word (`pattern`, `:valid`) | brick, front | typing "float" sets `--gy` 0 |
| camera select (`option:checked`) | cube, right | `--yaw`, or the orbit |
| reset everything | cube, left | `--rst` while held |
| disco | cube, bottom | every box's colour, stepped |
| mood radios, ⏻ / CH, 8-ball | brick side, TV side, a sphere | the box's own colour, the TV's screen, the sphere |

```bash
python3 experiments/widgets/build.py out/widgets.html      # (from css-physics/) + out/widgets-tv.webm
node experiments/widgets/check.js out/widgets.html         # clicks and typing reach the faces and the engine (BROWSER=firefox|webkit too)
node experiments/widgets/record.js out/widgets.html        # re-record tv.webm from the page itself, then rebuild
```

How it works:
- The engine's wrappers are `pointer-events: none`; a widget turns it back on. The scene paints above the grab grid
  (the wrappers are `z-index: 1`), so a widget under the pointer gets the press, and an empty part of a face lets it
  through to the grid, which grabs the body as usual. While a body is held (`.gr:active`) the widgets turn it off
  again, or a drag across one would take the hover away from the grid and the body would jump.
- Hit testing follows the 3D faces in Chrome, Firefox and WebKit, `backface-visibility` included.
- The arena is `overflow: clip`: focusing a widget near its edge scrolled the `overflow: hidden` arena.
- The TV plays a recording of this page (two passes of `record.js`: the TV shows itself).

Cost (`tools/tr.js`, 2026-10-22): a style pass with everything asleep goes from 0.3 to 0.55 ms (the
widgets' own animations: marquee, DVD logo, progress bar); awake (the drop scene), about 5 ms per pass with or without
them. 60 fps either way.
