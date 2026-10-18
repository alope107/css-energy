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
