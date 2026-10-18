# spheres.css: where a frame goes (2026-10-18)

128 spheres, `GAS=1` (no gravity, elastic: everything always moving), headless Chromium 153 on the mini PC, with another
browser session running (expect ±10%). Live frames from `node spheres/tools/frame.js page 1500 1500`; step-pass parts
from frozen pages (`FROZEN=snap.json FROZEN_MOVERS=0-127`, `ABL=nophys,nosort`, plus edits of the built page), compared
with `../shared/js/ab.js` (4–7 rotated rounds). A live frame is ~65 ms (15 fps): two style passes plus ~5 ms outside style.

## Step pass (the clock moved): ~36 ms

| Part | ms | How measured |
|---|---|---|
| physics (prediction, pair factors, gathers, tray, dead band) | 18.7 | frozen, `ABL=nophys` |
| sort (swap flags, phase-A x, and their share of the writebacks) | 3.9 | `nophys` → `nophys,nosort` |
| register writes (the sorted writeback expressions) | 4.8 | `nophys` → write rules stripped (holds kept) |
| activity flags on #LA (prefix chain C, ac/in/pa/ws/wr) | 1.7 | computed flags → constant flags |
| "anything moving" sum on #LT (3N `abs` terms) | 0.8 | sum removed |
| the rest: 640 gate rules on #LC, 450 register holds, #LT | ~5 | residual |

Copies for inactive slots (`p = n = x`, 7 trivial declarations each) cost ~3 µs per declaration (2.8 ms for 128
slots); they only exist in the sparse regime.

## Hold pass (the registers moved): ~24 ms

| Part | ms | How measured |
|---|---|---|
| render: 128 wrappers reading X/Y/Z/T with their own animations (512), 384 elements | ~10 | sphere markup removed |
| readback base values (`--X0: var(--ix0)` on the readback groups, only needed until the timelines resolve) | 6.5 | declarations removed (1.5 with the render also removed: the two interact) |
| readback animations (900, groups of 32), the 29-element chain, 450 register holds, #LT/#LA/#LC | ~11.5 | residual |

Readback group size barely matters (16: +2%, 128: −3%). Rendering from the readback chain (`RENDER=inh`) instead of
the wrappers' own animations: −8% hold pass in chaos (but it restyles every sphere on every hold pass, which costs
the sparse regime).

## Outside style: ~5 ms per frame

Animation servicing ~3 ms (2.3 without the render's animations), paint + layerize + commit ~2 ms (≈0 without the
render), layout ~0.5 ms.

## Totals

Physics is ~19 of ~65 ms. Everything else, ~46 ms (70%), is machinery: render ~12, readback ~18, register writes and
holds ~7, sort ~4, activity gating ~3, gate rules and the rest ~2.

## Render experiments (2026-10-18)

The page has two looks (radios): **neon** (default) is a canvas render, **classic** the billboard render above. (A
third, **toon**, was dropped: it painted in slot order, which drew far marbles over near ones.) A canvas render draws every sphere as entries in one `box-shadow` list on one element, at screen
positions projected through the camera in `calc()` (3 declarations per sphere), and every floor shadow as entries in
one `box-shadow` list on an element in the floor plane (no projection: the 3D transform does it). Neon blends
additively (`mix-blend-mode: plus-lighter`), so the list's paint order never shows. Each look sits in a container that is `display: none` when not
picked (on the elements themselves, `display: none` still styles them every pass, which made the hidden looks cost as
much as the shown one).

128 spheres, gas chaos (`frame.js`, 4–6 rotated rounds):

| Render | hold pass | fps |
|---|---|---|
| classic (wrappers read their registers with their own animations) | 24.6 ms | 15.3 |
| neon | 16.5 ms | 16.7–17.3 (+8 to +18%) |
| toon | 18.0 ms | 16.7 |
| no render at all | 13.4 ms | 18.7 |

Paint + layerize + commit fall from ~2.2 to ~0.8 ms per frame. Dragging one sphere through a settled 128 pile is about
even (classic 19–25 fps, neon 21): the canvas restyles as a whole every hold pass, the classic render only the spheres
that moved. Rendering is no longer a large item; the readback and the register writeback are.

## Bigger spread of sizes (2026-10-18)

Radii 7–24.5 (the biggest 3.5× the smallest, 6 sizes; was 13–17), contacts split by mass ((r/RMAX)³). The window must
now hold pairs up to two big radii apart: in the plain-JS model 1.15× the spheres in a 2 RMAX slab missed contacts at
192 and 256, 1.3× didn't, so K is 9 / 16 / 23 / 31 at 64 / 128 / 192 / 256 (was 6 / 10 / 15 / 19). At 128 in gas chaos
the step pass grew from ~36 to ~52 ms: classic 11–12 fps, neon 13 fps (+20%, hold pass 26 → 20 ms). No missed contacts,
no floor penetration; overlaps up to 8 px while 128 spheres pile up, under 1 px once settled.
