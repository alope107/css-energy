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
| readback base values (`--X0: var(--ix0)` on the readback groups, only needed until the timelines resolve) | ~0 | (an earlier "6.5 ms" came from a page whose render had stopped painting; moved to a static wrapper they measure 0.99) |
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

## Readback and register writes (2026-10-18)

**What a hold pass is made of** (frozen-hold pages: a wobbling snapshot read back on every pass, nothing stepping;
`FROZEN_HOLD=1`; 128 spheres, one-element render, 16.1 ms):

| Removed | ms | Implied |
|---|---|---|
| render (128 billboards + shadow canvas) | 9.8 | ~6 |
| the register elements (their timelines with them) | 9.8 | ~6 (≈13 µs per register element per pass, also just holding) |
| the registers' `var()` references (constant positions) | 12.0 | ~4 of those |
| the registers' gated rules (write, held flag, reset) | 15.1 | ~1.5 |
| #LC's gate rules (all false in a hold pass) | 14.1 | ~2 |
| the "anything moving" sum on #LT (3N `abs`) | 14.6 | ~1.5 |

**The readback animations themselves are cheap** (`experiments/mk_readback.py`: 450 register elements moved by a clock,
their 900 values read back): 2.2 ms over the 2.2 ms the moving registers cost alone, 2.4 µs per value. Groups of 8 are
+27%, all 900 on one element +16%, 32–128 per group best; `<integer>` or `<length>` instead of `<number>`, one
`timeline-scope` list or `timeline-scope: all` make no difference. No other channel beats this: the survey's grid ports
and size-container readers cost ~15 µs per value. The cost is in what restyles because a value changed.

**Every restyled element pays for the inherited custom properties it carries**: 2,000 set inherited registered
properties on an ancestor make the readback page 35% slower, 6,000 double it (that page restyles ~480 elements per
pass). The engine's lower elements carried ~3,500 at 128 spheres (readback, scene start values, solver outputs,
activity flags).

**Changes, measured end to end** (gas chaos, `frame.js`, 5 rotated rounds, against 9fe8106's classic render):

| Change | Effect |
|---|---|
| render: one billboard per sphere reading the readback chain, floor shadows on one box-shadow canvas (was a wrapper + 2 children reading 4 registers with their own animations) | together with the next three: **+16% fps at 128, +19% at 64**; hold pass 24.7 → 15.7 ms, step 51.7 → 47.4 ms |
| activity flags (C, ac, in, GH, wake) not inherited: only #LC's gates read them, on #LA | |
| a one-value "anything moved" register (AM) replaces the 384-term moving sum on #LT | |
| pairs and sort values in the active and copy blocks: two gate rules per slot instead of four | |
| scene start values as `if()` on one inherited scene number instead of 7 inherited properties per sphere | ±0 (1.00) |
| readback base values on a static wrapper (#LB) | ±0 (0.99) |

What remains of the machinery at 128: the 450 register elements (~6 ms per pass, twice per frame: they restyle on the
step pass to write and on the hold pass because the readback they inherit changed), the render (~6 ms), the sort
and register write expressions (~9 ms), #LC's gates (~2 ms per pass). The register elements can't skip the hold pass
while they sit under the readback chain, and they must, to read the solver's outputs.
